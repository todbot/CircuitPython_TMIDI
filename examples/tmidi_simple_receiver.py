# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example shows how to receive MIDI NoteOn and NoteOff messages

import usb_midi
import tmidi

midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])

while True:
    if msg := midi_usb.receive():
        if msg.type == tmidi.NOTE_ON and msg.velocity > 0:
            print(
                "note on: note:",
                msg.note,
                "vel:",
                msg.velocity,
                "channel:",
                msg.channel,
            )
        elif msg.type == tmidi.NOTE_OFF or msg.velocity == 0:
            print(
                "note off: note:",
                msg.note,
                "vel:",
                msg.velocity,
                "channel:",
                msg.channel,
            )
