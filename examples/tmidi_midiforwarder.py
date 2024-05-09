# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example is a simple USB-UART MIDI forwarder
# The serial MIDI is connected to TX/RX pins on a Feather or QTPy.
# You must wire up the needed resistors and MIDI jack yourself,
# or use the MIDI Feather wing.

import time
import board
import busio
import usb_midi

import tmidi

uart = busio.UART(rx=board.RX, tx=board.TX, baudrate=31250, timeout=0.001)
midi_uart = tmidi.MIDI(midi_in=uart, midi_out=uart)
midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])

print("waiting for midi...")
while True:
    msg = midi_usb.receive()
    if msg:
        print("usb:  %5.2f" % time.monotonic(), msg, ":", midi_usb.error_count)
        midi_uart.send(msg)

    msg = midi_uart.receive()
    if msg:
        print("uart: %5.2f" % time.monotonic(), msg, ":", midi_uart.error_count)
        midi_usb.send(msg)
