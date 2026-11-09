# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""Receive USB MIDI with callbacks, which avoids allocating Message objects"""

import usb_midi

import tmidi


def note_on(channel, note, velocity):
    print("note on: ", channel, note, velocity)


def note_off(channel, note, velocity):
    print("note off:", channel, note, velocity)


def cc(channel, control, value):
    print("cc:      ", channel, control, value)


midi = tmidi.MIDI(midi_in=usb_midi.ports[0])
midi.on(tmidi.NOTE_ON, note_on)
midi.on(tmidi.NOTE_OFF, note_off)
midi.on(tmidi.CC, cc)

print("tmidi callbacks, engine:", tmidi.ENGINE)
while True:
    midi.poll()
