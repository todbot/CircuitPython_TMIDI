# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
Round-trip test of a USB <-> UART MIDI interface running on a CircuitPython
board, through a USB-MIDI cable wired to the board's UART:

  host -> board USB -> board UART TX -> cable MIDI in -> host    (to_uart)
  host -> cable MIDI out -> board UART RX -> board USB -> host   (to_usb)

Checks every message type, 1000-message bursts each way and both ways at
once, round-trip times, and that the interface survives no app reading
the board's USB port.

On CIRCUITPY, make /tmidi_bench/ holding:
  tmidi/                       this repo's tmidi/
  tmidi_midi_interface.py      examples/tmidi_midi_interface/code.py, renamed
  fakeos.py                    from this directory
  adafruit_midi_interface.py   from this directory, for --impl adafruit,
  adafruit_midi/               with the adafruit_midi library

The board's code.py, boot.py and settings.toml aren't touched: the script
stops code.py, then runs the interface from the REPL with its settings
fed to os.getenv() by fakeos.py. Soft reset the board when done.

usage:
  pip install python-rtmidi pyserial
  python interface_trip_test.py --serial /dev/cu.usbmodem1101 \\
      --board "Pico CircuitPython" --cable "H2MIDI-Pro Port 1" \\
      ../examples/tmidi_midi_interface/settings_pico.toml \\
      TMIDI_UART_TX=GP16 TMIDI_UART_RX=GP17

--board and --cable match the start of the host's MIDI port names.
KEY=VALUE after the settings file overrides its settings.
"""

import argparse
import statistics
import time

import rtmidi
import serial

BOARD_DIR = "/tmidi_bench"

STATUS = {
    "NOTE_OFF": 0x80,
    "NOTE_ON": 0x90,
    "AFTERTOUCH": 0xA0,
    "CC": 0xB0,
    "CONTROLLER_CHANGE": 0xB0,
    "PROGRAM_CHANGE": 0xC0,
    "CHANNEL_PRESSURE": 0xD0,
    "PITCH_BEND": 0xE0,
    "SYSEX": 0xF0,
    "SYSTEM_EXCLUSIVE": 0xF0,
    "SONG_POSITION": 0xF2,
    "SONG_SELECT": 0xF3,
    "TUNE_REQUEST": 0xF6,
    "CLOCK": 0xF8,
    "START": 0xFA,
    "CONTINUE": 0xFB,
    "STOP": 0xFC,
    "ACTIVE_SENSING": 0xFE,
    "SYSTEM_RESET": 0xFF,
}

# adafruit_midi has no class for these
ADAFRUIT_UNSUPPORTED = {0xF2, 0xF3, 0xF6}

BIG_SYSEX = [0xF0, 0x7D] + [i & 0x7F for i in range(299)] + [0xF7]
MSGS = [
    [0x90, 60, 100],
    [0x80, 60, 0],
    [0xA1, 61, 50],
    [0xB2, 7, 99],
    [0xC3, 5],
    [0xD4, 77],
    [0xE5, 0x12, 0x34],
    [0xF2, 0x10, 0x20],
    [0xF3, 3],
    [0xF6],
    [0xF8],
    [0xFA],
    [0xFB],
    [0xFC],
    [0xFE],
    [0xFF],
    [0xF0, 0x7D] + list(range(10)) + [0xF7],
    BIG_SYSEX,
    [0x9F, 127, 127],
]


def load(path, overrides):
    """Raw text values, like CircuitPython 11 getenv()."""
    settings = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, val = (s.strip() for s in line.split("=", 1))
        if val.startswith('"'):
            val = val[1 : val.index('"', 1)]
        else:
            val = val.split("#")[0].strip()
        settings[key] = val
    for kv in overrides:
        key, val = kv.split("=", 1)
        settings[key] = val
    return settings


def drop_set(settings, key):
    names = [n.strip() for n in settings.get(key, "").split(",") if n.strip()]
    return {STATUS[n] for n in names}


def expected(msgs, drop, sysex_size):
    out = []
    for m in msgs:
        mtype = m[0] & 0xF0 if m[0] < 0xF0 else m[0]
        if mtype in drop:
            continue
        if mtype == 0xF0:
            if not sysex_size:
                continue
            m = [0xF0] + m[1:-1][:sysex_size] + [0xF7]
        out.append(m)
    return out


class Console:
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.1)
        self.log = ""

    def read_until(self, token, timeout):
        end = time.monotonic() + timeout
        buf = ""
        while time.monotonic() < end:
            buf += self.s.read(4096).decode(errors="replace")
            if token in buf:
                self.log += buf
                return buf
        self.log += buf
        raise SystemExit("console: no %r in:\n%s" % (token, buf[-1500:]))

    def drain(self):
        out = self.s.read(65536).decode(errors="replace")
        self.log += out
        return out

    def repl(self):
        self.s.write(b"\x03\x03")
        time.sleep(0.3)
        self.s.write(b"\r")
        self.read_until(">>> ", 10)

    def line(self, text, wait=">>> ", timeout=10):
        self.s.write(text.encode() + b"\r")
        return self.read_until(wait, timeout)

    def start(self, settings, impl):
        self.repl()
        self.s.write(b"\x04")  # soft reboot frees pins from any last run
        self.read_until("soft reboot", 10)
        time.sleep(1.5)
        self.repl()
        self.line("import sys; sys.path.insert(0, %r); import fakeos" % BOARD_DIR)
        self.line("fakeos.SETTINGS.update(%r); sys.modules['os'] = fakeos" % settings)
        if impl == "python":
            self.line("import tmidi; tmidi._kernel_parse = None")
        module = (
            "adafruit_midi_interface" if impl == "adafruit" else "tmidi_midi_interface"
        )
        out = self.line("import " + module, wait="drop to usb:", timeout=30)
        time.sleep(0.3)
        return out + self.drain()

    def stop(self):
        self.s.write(b"\x03")
        return self.read_until(">>> ", 10)


def open_port(cls, name):
    p = cls()
    names = p.get_ports()
    i = next((i for i, n in enumerate(names) if n.startswith(name)), None)
    if i is None:
        raise SystemExit("no MIDI port %r in %s" % (name, names))
    p.open_port(i)
    if cls is rtmidi.MidiIn:
        p.ignore_types(sysex=False, timing=False, active_sense=False)
    return p


def collect(inn, timeout, want=None):
    got = []
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        m = inn.get_message()
        if m:
            got.append(m[0])
            if want is not None and len(got) >= want:
                break
        else:
            time.sleep(0.0005)
    return got


def flush(*ins):
    for inn in ins:
        while inn.get_message():
            pass


def check(label, got, want):
    ok = got == want
    print("  %-28s %s (%d of %d)" % (label, "ok" if ok else "FAIL", len(got), len(want)))
    if not ok:
        for i, (g, w) in enumerate(zip(got, want)):
            if g != w:
                print("    first diff at %d: got %s want %s" % (i, g[:8], w[:8]))
                break
        if len(got) != len(want):
            print(
                "    extra/missing:",
                [m[:8] for m in (got[len(want) :] or want[len(got) :])[:5]],
            )
    return ok


def burst(n, base_ch=0):
    return [
        [0x90 | ((i + base_ch) & 15), i & 127, (i // 128) % 127 + 1] for i in range(n)
    ]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--serial", required=True, help="the board's REPL serial port")
    ap.add_argument("--board", required=True, help="the board's MIDI port name")
    ap.add_argument("--cable", required=True, help="the USB-MIDI cable's MIDI port name")
    ap.add_argument("--impl", choices=("viper", "python", "adafruit"), default="viper")
    ap.add_argument("settings", help="settings.toml for the interface")
    ap.add_argument("overrides", nargs="*", help="KEY=VALUE settings")
    args = ap.parse_args()

    settings = load(args.settings, args.overrides)
    sysex_size = int(settings.get("TMIDI_SYSEX_SIZE", "256"), 0)
    drop_uart = drop_set(settings, "TMIDI_FILTER_TO_UART")
    drop_usb = drop_set(settings, "TMIDI_FILTER_TO_USB")
    if args.impl == "adafruit":
        drop_uart |= ADAFRUIT_UNSUPPORTED
        drop_usb |= ADAFRUIT_UNSUPPORTED

    con = Console(args.serial)
    print(con.start(settings, args.impl).strip().replace("\r", ""))
    board_out = open_port(rtmidi.MidiOut, args.board)
    board_in = open_port(rtmidi.MidiIn, args.board)
    cable_out = open_port(rtmidi.MidiOut, args.cable)
    cable_in = open_port(rtmidi.MidiIn, args.cable)
    time.sleep(0.3)
    results = []

    for label, out, inn, drop in (
        ("to_uart: every type", board_out, cable_in, drop_uart),
        ("to_usb: every type", cable_out, board_in, drop_usb),
    ):
        flush(board_in, cable_in)
        for m in MSGS:
            out.send_message(m)
            time.sleep(0.03)
        results.append(check(label, collect(inn, 1.0), expected(MSGS, drop, sysex_size)))

    n = 1000
    for label, out, inn in (
        ("to_uart: burst of %d" % n, board_out, cable_in),
        ("to_usb: burst of %d" % n, cable_out, board_in),
    ):
        flush(board_in, cable_in)
        msgs = burst(n)
        t0 = time.monotonic()
        for m in msgs:
            out.send_message(m)
        got = collect(inn, 5.0, want=n)
        results.append(check(label, got, msgs))
        print("    %.2f s, wire minimum %.2f s" % (time.monotonic() - t0, n * 30 / 31250))

    flush(board_in, cable_in)
    a, b = burst(n), burst(n, base_ch=8)
    for ma, mb in zip(a, b):
        board_out.send_message(ma)
        cable_out.send_message(mb)
    got_uart, got_usb = [], []
    end = time.monotonic() + 6
    while time.monotonic() < end and (len(got_uart) < n or len(got_usb) < n):
        for inn, got in ((cable_in, got_uart), (board_in, got_usb)):
            m = inn.get_message()
            if m:
                got.append(m[0])
        time.sleep(0.0002)
    results.append(check("both ways at once: to_uart", got_uart, a))
    results.append(check("both ways at once: to_usb", got_usb, b))

    for label, out, inn in (
        ("to_uart", board_out, cable_in),
        ("to_usb", cable_out, board_in),
    ):
        flush(board_in, cable_in)
        trips = []
        for i in range(50):
            t0 = time.perf_counter()
            out.send_message([0x90, i, 64])
            if collect(inn, 0.5, want=1):
                trips.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.01)
        print(
            "  %s trip ms: median %.2f, max %.2f (%d of 50, incl. cable and host)"
            % (label, statistics.median(trips), max(trips), len(trips))
        )

    # usb_midi writes return 0 while no app on the host reads the board's port
    board_in.close_port()
    t0 = time.monotonic()
    for _ in range(3):
        cable_out.send_message(BIG_SYSEX)
    for i in range(20):
        cable_out.send_message([0x90, i, 1])
    time.sleep(1.0)
    still = [[0x91, i, 2] for i in range(10)]
    for m in still:
        board_out.send_message(m)
    got = collect(cable_in, 2.0, want=len(still))
    results.append(check("no USB reader: to_uart alive", got, still))
    print("    to_uart answered %.2f s after the SysEx went in" % (time.monotonic() - t0))
    board_in = open_port(rtmidi.MidiIn, args.board)
    time.sleep(0.3)
    flush(board_in)
    for m in still:
        cable_out.send_message(m)
    results.append(check("no USB reader: to_usb after", collect(board_in, 1.0), still))

    tail = con.drain() + con.stop()
    errors = [
        ln for ln in tail.splitlines() if "Error" in ln and "KeyboardInterrupt" not in ln
    ]
    print("  console errors:", errors or "none")
    print("ALL OK" if all(results) and not errors else "FAILURES")


main()
