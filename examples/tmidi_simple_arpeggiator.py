# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example shows both receiving and sending MIDI messages
# by implementing a simple arpeggiator.
# MIDI notes send to MIDI In are arpeggiated to MIDI Output.

import time
import usb_midi
import tmidi
from tmidi import NOTE_ON, NOTE_OFF

midi = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])
# if serial midi
# uart = busio.UART(rx=board.RX, tx=board.TX, timeout=0.001)
# midi = tmidi.MIDI(midi_in=uart, midi_out=uart)

tempo = 120  # bpm
notes_per_beat = 2  # 1 = quarter-note, 2 = 8th, 4 = 16th
note_time = 60 / tempo / notes_per_beat  # seconds between arp notes
gate_percent = 0.5  # fraction of note_time each arp note sounds

pressed_notes = []  # notes held down, in the order pressed
note_i = 0  # index in pressed_notes
last_note_time = 0  # when the current arp note started
gate_time = 0  # how long in secs the current arp note sounds, 0 once it's off


def note_off(channel, note, velocity):
    global note_i
    if note in pressed_notes:
        midi.send(tmidi.Message(NOTE_OFF, note, velocity, channel))
        pressed_notes.remove(note)
        note_i = 0


def note_on(channel, note, velocity):
    if velocity == 0:
        note_off(channel, note, velocity)
        return
    print("note on", note, velocity)
    pressed_notes.append(note)


midi.on(NOTE_ON, note_on)
midi.on(NOTE_OFF, note_off)

while True:
    midi.poll()

    # do midi output, if we have pressed notes
    if len(pressed_notes) == 0:
        continue

    now = time.monotonic()
    if now - last_note_time >= note_time:
        last_note_time = now
        note_on = tmidi.Message(NOTE_ON, pressed_notes[note_i], 127)
        print("arp note_on: ", note_on)
        midi.send(note_on)
        gate_time = note_time * gate_percent

    if gate_time > 0 and now - last_note_time >= gate_time:
        gate_time = 0
        note_off = tmidi.Message(NOTE_OFF, pressed_notes[note_i], 127)
        print("arp note_off:", note_off)
        midi.send(note_off)
        note_i = (note_i + 1) % len(pressed_notes)
