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
#     4. Run tmidi_test_host.py --serial /dev/cu.usbmodemXXXX on the host
#        (or use a hardware MIDI loopback at 31250 baud).

import board
import busio
import digitalio
import usb_midi

import tmidi

MODE = "usb_midi"  # "usb_midi" | "usb_cdc" | "uart"

UART_TX = board.TX  # override for non-default pins
UART_RX = board.RX

# ---- setup -----------------------------------------------------------------

try:
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
except AttributeError:
    led = None  # board has no LED pin

if MODE == "usb_midi":
    midi = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])
    print("tmidi_test_device: USB MIDI mode")

elif MODE == "usb_cdc":
    import usb_cdc  # noqa: E402

    midi = tmidi.MIDI(midi_in=usb_cdc.data, midi_out=usb_cdc.data)
    print("tmidi_test_device: USB CDC serial mode")

elif MODE == "uart":
    uart = busio.UART(tx=UART_TX, rx=UART_RX, baudrate=31250, timeout=0)
    midi = tmidi.MIDI(midi_in=uart, midi_out=uart)
    print(f"tmidi_test_device: UART mode (TX={UART_TX} RX={UART_RX})")

else:
    raise ValueError(f"Unknown MODE: {MODE!r} — must be 'usb_midi', 'usb_cdc', or 'uart'")

print("Echoing MIDI (SysEx consumed but not echoed).")

# ---- main loop -------------------------------------------------------------

msg_count = 0
last_errors = 0

while True:
    msg = midi.receive()
    if msg is None:
        continue

    if led:
        led.value = True

    msg_count += 1
    print(msg_count, msg)

    if msg.type != tmidi.SYSEX:
        midi.send(msg)

    if led:
        led.value = False

    if midi.error_count != last_errors:
        last_errors = midi.error_count
        print("  parse errors:", last_errors)
