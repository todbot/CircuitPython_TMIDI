# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
examples/tmidi_midi_interface/code.py done the usual adafruit_midi way,
receive() then send(), to compare the two with interface_trip_test.py.
Reads the same TMIDI_UART_TX and TMIDI_UART_RX settings, plus AF_IN_BUF
for adafruit_midi's in_buf_size.
"""

import os

import adafruit_midi
import board
import busio
import usb_midi
from adafruit_midi.active_sensing import ActiveSensing  # noqa: F401
from adafruit_midi.channel_pressure import ChannelPressure  # noqa: F401
from adafruit_midi.control_change import ControlChange  # noqa: F401
from adafruit_midi.midi_continue import Continue  # noqa: F401
from adafruit_midi.midi_message import MIDIBadEvent, MIDIUnknownEvent
from adafruit_midi.midi_reset import Reset  # noqa: F401
from adafruit_midi.mtc_quarter_frame import MtcQuarterFrame  # noqa: F401
from adafruit_midi.note_off import NoteOff  # noqa: F401
from adafruit_midi.note_on import NoteOn  # noqa: F401
from adafruit_midi.pitch_bend import PitchBend  # noqa: F401
from adafruit_midi.polyphonic_key_pressure import PolyphonicKeyPressure  # noqa: F401
from adafruit_midi.program_change import ProgramChange  # noqa: F401
from adafruit_midi.start import Start  # noqa: F401
from adafruit_midi.stop import Stop  # noqa: F401
from adafruit_midi.system_exclusive import SystemExclusive  # noqa: F401
from adafruit_midi.timing_clock import TimingClock  # noqa: F401

IN_BUF = int(os.getenv("AF_IN_BUF", "30"))

uart = busio.UART(
    tx=getattr(board, os.getenv("TMIDI_UART_TX", "TX")),
    rx=getattr(board, os.getenv("TMIDI_UART_RX", "RX")),
    baudrate=31250,
    timeout=0.001,
    receiver_buffer_size=512,
)
to_uart = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], midi_out=uart, in_buf_size=IN_BUF)
to_usb = adafruit_midi.MIDI(midi_in=uart, midi_out=usb_midi.ports[1], in_buf_size=IN_BUF)
links = (to_uart, to_usb)
# no class for these, so they can't be sent
skip = (MIDIUnknownEvent, MIDIBadEvent)

print("adafruit_midi_interface, in_buf_size", IN_BUF)
# interface_trip_test.py waits for this line
print("drop to usb: ")

while True:
    for link in links:
        msg = link.receive()
        if msg is not None and not isinstance(msg, skip):
            link.send(msg, channel=msg.channel)
