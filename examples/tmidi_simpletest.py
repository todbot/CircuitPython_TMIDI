# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example outputs MIDI notes over USB MIDI

import time
import random
import usb_midi

import tmidi

midi_channel = 1  # which MIDI channel to send on

midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])

while True:
    notenum = random.randint(36, 72)
    velocity = 127

    msg_on = tmidi.Message(tmidi.NOTE_ON, notenum, velocity, channel=midi_channel - 1)
    print("sending note on  msg:", msg_on)
    midi_usb.send(msg_on)
    time.sleep(0.1)

    msg_off = tmidi.Message(tmidi.NOTE_OFF, notenum, 0, channel=midi_channel - 1)
    print("sending note off msg:", msg_off)
    midi_usb.send(msg_off)
    time.sleep(0.2)
