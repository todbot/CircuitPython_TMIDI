# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example shows how to receive MIDI NoteOn, NoteOff and CC messages
# with callbacks and poll(), which avoids allocating Message objects

import usb_midi
import tmidi


def note_on(channel, note, velocity):
    if velocity == 0:  # many devices send note off as a velocity 0 note on
        note_off(channel, note, velocity)
        return
    print(f"note on: note: {note} vel: {velocity} chan: {channel}")


def note_off(channel, note, velocity):
    print(f"note off: note: {note} vel: {velocity} chan: {channel}")


def cc(channel, control, value):
    print(f"cc: num: {control} val: {value} chan: {channel}")


midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0])
midi_usb.on(tmidi.NOTE_ON, note_on)
midi_usb.on(tmidi.NOTE_OFF, note_off)
midi_usb.on(tmidi.CC, cc)

while True:
    midi_usb.poll()
