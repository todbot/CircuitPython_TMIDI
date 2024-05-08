# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

import time
import random
import usb_midi

import tmidi

midi_channel = 1  # which MIDI channel to send on

midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])

while True:
    notenum = random.randint(36, 72)
    velocity = 127

    msg_on = tmidi.Message(tmidi.NOTE_ON, midi_channel - 1, notenum, velocity)
    midi_usb.send(msg_on)
    time.sleep(0.1)

    msg_off = tmidi.Message(tmidi.NOTE_OFF, midi_channel - 1, notenum, 0)
    midi_usb.send(msg_off)
    time.sleep(0.2)
