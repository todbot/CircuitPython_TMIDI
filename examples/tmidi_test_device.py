# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

# MIDI echo server for hardware-in-the-loop testing with tmidi_test_host.py.
#
# Receives every MIDI message and echoes it back unchanged, except SysEx
# which is consumed-and-discarded (parser reads until 0xF7 to stay in sync).
#
# Three modes — set MODE below:
#
#   "usb_midi" (default):
#     Just plug in and run tmidi_test_host.py --usb-midi on the host.
#
#   "usb_cdc" (simulates busio.UART byte stream over USB):
#     1. Put this in boot.py on the device:
#          import usb_cdc
#          usb_cdc.enable(console=True, data=True)
#     2. Set MODE = "usb_cdc" below.
#     3. Run tmidi_test_host.py --serial /dev/cu.usbmodemXXXX on the host.
#        (The REPL is on the first CDC port; use the *second* one for MIDI.)
#
#   "uart" (hardware UART / TRS MIDI):
#     1. Set MODE = "uart" below.
#     2. Optionally override UART_TX and UART_RX to use different pins.
#     3. Connect a MIDI interface circuit to those pins.
#     4. Run tmidi_test_host.py --usb-midi with --port and --in-port set to
#        a USB MIDI interface wired to those pins, e.g.
#          --port "RK006 OUT_ALL" --in-port "RK006 IN_ALL"
#
# With CHECK_WIRE, every byte read is logged and, once input goes quiet,
# parsed again with the pure Python parser. A mismatch is a tmidi bug, while
# a test failure without one comes from the interface or the wiring.

import time

import board
import busio
import digitalio
import usb_midi

import tmidi

MODE = "usb_midi"  # "usb_midi" | "usb_cdc" | "uart"

UART_TX = board.TX  # override for non-default pins, e.g. board.GP16 on a Pico
UART_RX = board.RX

VERBOSE = False  # print every message; slow enough to overflow UART in bursts
CHECK_WIRE = True

# ---- setup -----------------------------------------------------------------


class WireLog:
    """Port wrapper that logs every byte tmidi reads"""

    def __init__(self, port):
        self.port = port
        self.log = bytearray()

    @property
    def in_waiting(self):
        return getattr(self.port, "in_waiting", 64)

    def readinto(self, buf, nbytes):
        n = self.port.readinto(buf, nbytes) or 0
        if n:
            self.log.extend(memoryview(buf)[:n])
        return n


class Replay:
    def __init__(self, data):
        self.data = memoryview(data)

    def readinto(self, buf, nbytes):
        n = min(nbytes, len(self.data))
        buf[:n] = self.data[:n]
        self.data = self.data[n:]
        return n


def msg_tuple(msg):
    return (msg.type, msg.channel, msg.data0, msg.data1)


def check_wire(wire, seen):
    reparse = tmidi.MIDI(
        midi_in=Replay(wire.log), sysex_buffer=bytearray(128), turbo=False
    )
    expect = []
    while msg := reparse.receive():
        expect.append(msg_tuple(msg))
    if expect == seen:
        print("wire check OK: %d bytes, %d msgs" % (len(wire.log), len(seen)))
    else:
        print("WIRE CHECK MISMATCH: %d bytes" % len(wire.log))
        for i, (e, s) in enumerate(zip(expect, seen)):
            if e != s:
                print("  first diff at msg %d: wire %s, tmidi %s" % (i, e, s))
                break
        else:
            print("  wire %d msgs, tmidi %d msgs" % (len(expect), len(seen)))
    wire.log = bytearray()
    seen.clear()


try:
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
except AttributeError:
    led = None  # board has no LED pin

if MODE == "usb_midi":
    midi_in, midi_out = usb_midi.ports[0], usb_midi.ports[1]
    print("tmidi_test_device: USB MIDI mode")

elif MODE == "usb_cdc":
    import usb_cdc  # noqa: E402

    midi_in = midi_out = usb_cdc.data
    print("tmidi_test_device: USB CDC serial mode")

elif MODE == "uart":
    midi_in = midi_out = busio.UART(tx=UART_TX, rx=UART_RX, baudrate=31250, timeout=0)
    print(f"tmidi_test_device: UART mode (TX={UART_TX} RX={UART_RX})")

else:
    raise ValueError(f"Unknown MODE: {MODE!r} — must be 'usb_midi', 'usb_cdc', or 'uart'")

wire = WireLog(midi_in) if CHECK_WIRE else None
midi = tmidi.MIDI(midi_in=wire or midi_in, midi_out=midi_out, sysex_buffer=bytearray(128))
print("Echoing MIDI (SysEx consumed but not echoed), parser:", tmidi.ENGINE)

# ---- main loop -------------------------------------------------------------

msg_count = 0
last_errors = 0
seen = []
last_msg_time = 0

while True:
    msg = midi.receive()
    if msg is None:
        if wire and wire.log and time.monotonic() - last_msg_time > 0.5:
            check_wire(wire, seen)
        continue
    last_msg_time = time.monotonic()

    if led:
        led.value = True

    msg_count += 1
    if VERBOSE:
        print(msg_count, msg)
    if wire:
        seen.append(msg_tuple(msg))

    if msg.type != tmidi.SYSEX:
        midi.send(msg)

    if led:
        led.value = False

    if midi.error_count != last_errors:
        last_errors = midi.error_count
        print("  parse errors:", last_errors)
