# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# MIDI echo server for hardware-in-the-loop testing with tmidi_test_host.py.
#
# Receives every MIDI message and echoes it back unchanged, except SysEx
# which is consumed-and-discarded (parser reads until 0xF7 to stay in sync).
#
# Two modes — change USE_USB_MIDI below:
#
#   USB MIDI (default):
#     Just plug in and run tmidi_test_host.py --usb-midi on the host.
#
#   USB CDC serial (simulates busio.UART byte stream):
#     1. Put this in boot.py on the device:
#          import usb_cdc
#          usb_cdc.enable(console=True, data=True)
#     2. Set USE_USB_MIDI = False below.
#     3. Run tmidi_test_host.py --serial /dev/cu.usbmodemXXXX on the host.
#        (The REPL is on the first CDC port; use the *second* one for MIDI.)

import board
import digitalio
import usb_midi

import tmidi

USE_USB_MIDI = True

# ---- setup -----------------------------------------------------------------

try:
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
except AttributeError:
    led = None  # board has no LED pin

if USE_USB_MIDI:
    midi = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])
    print("tmidi_test_device: USB MIDI mode")
else:
    import usb_cdc  # noqa: E402

    midi = tmidi.MIDI(midi_in=usb_cdc.data, midi_out=usb_cdc.data)
    print("tmidi_test_device: USB CDC serial mode")

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
