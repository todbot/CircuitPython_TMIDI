# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example shows how to receive MIDI from multiple devices,
# in this case USB MIDI and serial MIDI.
# The serial MIDI is connected to TX/RX pins on a Feather or QTPy.
# You must wire up the needed resistors and MIDI jack yourself,
# or use the MIDI Feather wing.

import time
import board
import busio
import usb_midi

import tmidi

uart = busio.UART(rx=board.RX, tx=board.TX, baudrate=31250, timeout=0.001)
midi_uart = tmidi.MIDI(midi_in=uart)
midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0])

last_time = 0
while True:
    if time.monotonic() - last_time > 1.0:
        last_time = time.monotonic()
        print("waiting for midi on either usb or uart...")

    if msg := midi_usb.receive() or midi_uart.receive():
        print("%5.2f" % time.monotonic(), msg)
