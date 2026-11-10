#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# MIDI hardware-in-the-loop test host.
#
# Sends a battery of MIDI messages to a CircuitPython RP2040 running
# tmidi_test_device.py and verifies the echoed replies match.
#
# Usage:
#   python tmidi_test_host.py --usb-midi [--port "CircuitPython Audio"]
#   python tmidi_test_host.py --usb-midi --port "RK006 OUT_ALL" --in-port "RK006 IN_ALL"
#   python tmidi_test_host.py --serial /dev/cu.usbmodemXXXX
#   python tmidi_test_host.py --serial /dev/ttyACM1
#
# The second form tests the device's UART MIDI through a USB MIDI interface.
#
# Dependencies:
#   USB MIDI mode:  pip install mido python-rtmidi
#   Serial mode:    pip install pyserial

import argparse
import sys
import time

ECHO_TIMEOUT = 2.0  # seconds to wait for each echo

# ---------------------------------------------------------------------------
# Test cases
#
# Each entry: (description, [send_bytes, ...], expect_bytes)
#   send_bytes  — list of raw MIDI byte sequences to send in order
#   expect_bytes — raw bytes expected as the echo, or None for no echo
#
# Pitch bend encoding (standard MIDI, LSB first):
#   center (0)    [0xE0, 0x00, 0x40]   (14-bit value 0x2000 = 8192)
#   full up (+8191) [0xE0, 0x7F, 0x7F] (14-bit value 0x3FFF)
#   full down (-8192) [0xE0, 0x00, 0x00] (14-bit value 0x0000)
# ---------------------------------------------------------------------------

TESTS = [
    (
        "NOTE_ON ch=0 note=60 vel=100",
        [bytes([0x90, 60, 100])],
        bytes([0x90, 60, 100]),
    ),
    (
        "NOTE_OFF ch=0 note=60 vel=0",
        [bytes([0x80, 60, 0])],
        bytes([0x80, 60, 0]),
    ),
    (
        "CONTROL_CHANGE ch=3 cc=74 val=64",
        [bytes([0xB3, 74, 64])],
        bytes([0xB3, 74, 64]),
    ),
    (
        "PROGRAM_CHANGE ch=5 prog=42",
        [bytes([0xC5, 42])],
        bytes([0xC5, 42]),
    ),
    (
        "PITCH_BEND ch=0 center (0)",
        [bytes([0xE0, 0x00, 0x40])],
        bytes([0xE0, 0x00, 0x40]),
    ),
    (
        "PITCH_BEND ch=0 full up (+8191)",
        [bytes([0xE0, 0x7F, 0x7F])],
        bytes([0xE0, 0x7F, 0x7F]),
    ),
    (
        "PITCH_BEND ch=0 full down (-8192)",
        [bytes([0xE0, 0x00, 0x00])],
        bytes([0xE0, 0x00, 0x00]),
    ),
    (
        "NOTE_ON ch=15 note=0 vel=127",
        [bytes([0x9F, 0, 127])],
        bytes([0x9F, 0, 127]),
    ),
    (
        "NOTE_ON ch=0 note=61 vel=0",
        [bytes([0x90, 61, 0])],
        bytes([0x90, 61, 0]),
    ),
    (
        "AFTERTOUCH ch=2 note=64 val=33",
        [bytes([0xA2, 64, 33])],
        bytes([0xA2, 64, 33]),
    ),
    (
        "CHANNEL_PRESSURE ch=7 val=99",
        [bytes([0xD7, 99])],
        bytes([0xD7, 99]),
    ),
    (
        "SONG_POSITION lsb=0x20 msb=0x20",
        [bytes([0xF2, 0x20, 0x20])],
        bytes([0xF2, 0x20, 0x20]),
    ),
    (
        "SONG_SELECT 5",
        [bytes([0xF3, 5])],
        bytes([0xF3, 5]),
    ),
    (
        "CLOCK (single-byte real-time)",
        [bytes([0xF8])],
        bytes([0xF8]),
    ),
    (
        "START",
        [bytes([0xFA])],
        bytes([0xFA]),
    ),
    (
        "STOP",
        [bytes([0xFC])],
        bytes([0xFC]),
    ),
    (
        # 0x7D is "non-commercial": a Universal SysEx like device inquiry
        # may get answered by something else on a MIDI chain
        "SYSEX desync: NOTE_ON must survive a SysEx burst (ch=2, note=85, vel=99)",
        [
            bytes([0xF0, 0x7D, 0x01, 0x02, 0x03, 0xF7]),  # SysEx — consumed, not echoed
            bytes([0x92, 85, 99]),  # NOTE_ON — must be echoed cleanly
        ],
        bytes([0x92, 85, 99]),
    ),
    (
        "SYSEX longer than one read: 100 bytes, then CC",
        [
            bytes([0xF0] + list(range(100)) + [0xF7]),
            bytes([0xB0, 1, 2]),
        ],
        bytes([0xB0, 1, 2]),
    ),
]


def _burst():
    msgs = []
    for i in range(200):
        msgs.append(bytes([0x90, 36 + i % 48, 1 + i % 127]))
        msgs.append(bytes([0x80, 36 + i % 48, 0]))
        if i % 10 == 0:
            msgs.append(bytes([0xF8]))
            msgs.append(bytes([0xB2, 7, i % 128]))
    return msgs


BURST = _burst()
# Burst messages go out at MIDI's 31250 baud, so a UART device gets them
# back to back. Sending faster made an RK006 drop its input while busy.
BAUD_SECS_PER_BYTE = 10 / 31250


# ---------------------------------------------------------------------------
# USB MIDI transport — uses mido + python-rtmidi
# ---------------------------------------------------------------------------


class MidiTransportUSB:
    def __init__(self, port_name=None, in_port_name=None):
        try:
            import mido
        except ImportError:
            sys.exit("ERROR: mido not installed. Run: pip install mido python-rtmidi")
        self._mido = mido

        out_names = mido.get_output_names()
        in_names = mido.get_input_names()

        if not out_names:
            sys.exit("ERROR: No MIDI output ports found. Is the device plugged in?")

        if port_name is None:
            keywords = ("circuit", "pico", "tmidi")
            for kw in keywords:
                hits = [n for n in out_names if kw in n.lower()]
                if hits:
                    port_name = hits[0]
                    break
            if port_name is None:
                print("Available MIDI output ports:")
                for n in out_names:
                    print("  ", n)
                sys.exit("Use --port to specify one.")

        # Match the input port by name (may have a numeric suffix on some OSes)
        in_name = in_port_name or next(
            (n for n in in_names if port_name in n or n in port_name),
            in_names[0] if in_names else port_name,
        )

        print("Output ->", port_name)
        print("Input  <-", in_name)
        self._out = mido.open_output(port_name)
        self._inp = mido.open_input(in_name)

    def send(self, raw_bytes):
        for msg in self._mido.parse_all(raw_bytes):
            self._out.send(msg)

    def receive(self, timeout=ECHO_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self._inp.receive(block=False)
            if msg is not None:
                return bytes(msg.bytes())
            time.sleep(0.001)
        return None

    def close(self):
        self._out.close()
        self._inp.close()


# ---------------------------------------------------------------------------
# Serial transport — uses pyserial (USB CDC or physical UART)
# ---------------------------------------------------------------------------


class MidiTransportSerial:
    # Data byte counts for parsing the raw MIDI byte stream on the host.
    _DATA_LEN = {
        0x80: 2,
        0x90: 2,
        0xA0: 2,
        0xB0: 2,
        0xC0: 1,
        0xD0: 1,
        0xE0: 2,
        0xF2: 2,
        0xF3: 1,
        0xF5: 1,
    }

    def __init__(self, port_path):
        try:
            import serial
        except ImportError:
            sys.exit("ERROR: pyserial not installed. Run: pip install pyserial")
        # Baud rate is nominal for USB CDC (USB ignores it); use 31250 for
        # a physical UART connected to a hardware MIDI port.
        self._ser = serial.Serial(port_path, 115200, timeout=0.05)
        print("Serial port:", port_path)
        time.sleep(0.5)  # let the device settle after the port opens
        self._ser.reset_input_buffer()

    def send(self, raw_bytes):
        self._ser.write(raw_bytes)

    def receive(self, timeout=ECHO_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            b = self._ser.read(1)
            if not b:
                continue
            status = b[0]
            if not (status & 0x80):
                continue  # skip stray data bytes
            msg_type = status & 0xF0 if status < 0xF0 else status
            data_len = self._DATA_LEN.get(msg_type, 0)
            data = self._ser.read(data_len) if data_len else b""
            return bytes([status]) + data
        return None

    def close(self):
        self._ser.close()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_tests(transport):
    passed = 0
    failed = 0

    for i, (name, send_seqs, expect) in enumerate(TESTS, 1):
        print("[%d/%d] %s ... " % (i, len(TESTS), name), end="", flush=True)
        t0 = time.monotonic()

        for raw in send_seqs:
            transport.send(raw)
            time.sleep(0.01)  # small gap so burst messages don't merge

        if expect is None:
            time.sleep(0.05)
            print("OK (no echo)")
            passed += 1
            continue

        reply = transport.receive()
        # real-time can arrive at any time, e.g. clock from an interface
        while reply and reply[0] >= 0xF8 and expect[0] < 0xF8:
            reply = transport.receive()
        elapsed_ms = (time.monotonic() - t0) * 1000

        if reply is None:
            print("FAIL (timeout after %.1fs)" % ECHO_TIMEOUT)
            failed += 1
        elif bytes(reply) == bytes(expect):
            print("PASS (%.0f ms)" % elapsed_ms)
            passed += 1
        else:
            exp_hex = " ".join("%02X" % b for b in expect)
            got_hex = " ".join("%02X" % b for b in reply)
            print("FAIL (expected %s, got %s)" % (exp_hex, got_hex))
            failed += 1

        time.sleep(0.02)  # inter-test gap

    total = len(TESTS) + 1
    print(
        "[%d/%d] BURST of %d messages ... " % (total, total, len(BURST)),
        end="",
        flush=True,
    )
    if run_burst(transport):
        passed += 1
    else:
        failed += 1

    print()
    result = "PASSED" if failed == 0 else "FAILED"
    print("%s: %d/%d tests" % (result, passed, total))
    return failed == 0


def run_burst(transport):
    due = time.perf_counter()
    for raw in BURST:
        transport.send(raw)
        due += len(raw) * BAUD_SECS_PER_BYTE
        while time.perf_counter() < due:
            pass
    replies = []
    while (reply := transport.receive(timeout=1.0)) is not None:
        replies.append(bytes(reply))

    # Real-time messages may jump ahead of others in transit, and some
    # interfaces add or drop clocks, so they are only reported
    def split(msgs):
        return [m for m in msgs if m[0] < 0xF8], sum(m[0] >= 0xF8 for m in msgs)

    want, want_rt = split(BURST)
    got, got_rt = split(replies)
    counts = "sent %d + %d real-time, got %d + %d" % (
        len(want),
        want_rt,
        len(got),
        got_rt,
    )
    if got == want:
        print("PASS (%s)" % counts)
        return True
    print("FAIL (%s)" % counts)
    for i, (w, g) in enumerate(zip(want, got)):
        if w != g:
            print("  first diff at %d: expected %s, got %s" % (i, w.hex(" "), g.hex(" ")))
            break
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="tmidi hardware-in-the-loop test host",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --usb-midi
  %(prog)s --usb-midi --port "CircuitPython Audio"
  %(prog)s --serial /dev/cu.usbmodemXXXX   (macOS)
  %(prog)s --serial /dev/ttyACM1            (Linux)
""",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--usb-midi",
        action="store_true",
        help="test via USB MIDI (requires mido + python-rtmidi)",
    )
    mode.add_argument(
        "--serial", metavar="PORT", help="test via serial port (requires pyserial)"
    )
    parser.add_argument(
        "--port", metavar="NAME", help="MIDI output port name (--usb-midi only)"
    )
    parser.add_argument(
        "--in-port",
        metavar="NAME",
        help="MIDI input port name, if it doesn't match --port (--usb-midi only)",
    )
    args = parser.parse_args()

    print("tmidi hardware-in-the-loop test")
    print("=" * 40)

    if args.usb_midi:
        transport = MidiTransportUSB(port_name=args.port, in_port_name=args.in_port)
    else:
        transport = MidiTransportSerial(args.serial)

    print()
    try:
        ok = run_tests(transport)
    except KeyboardInterrupt:
        print("\nAborted.")
        ok = False
    finally:
        transport.close()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
