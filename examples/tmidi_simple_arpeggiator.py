# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

# This example shows both receiving and sending MIDI messages
# by implementing a simple arpeggiator.
# MIDI notes send to MIDI In are arpeggiated to MIDI Output.

import time
import usb_midi
import tmidi

midi = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])
# if serial midi
# uart = busio.UART(rx=board.RX, tx=board.TX, timeout=0.000)
# midi = tmidi.MIDI(midi_in=uart, midi_out=uart)

tempo = 120  # bpm
notes_per_beat = 2  # 1 = quarter-note, 2 = 8th, 4 = 16th
note_time = 60 / tempo / notes_per_beat
gate_percent = 0.5

pressed_notes = []
note_i = 0
last_note_time = 0
gate_time = 0
while True:
    # handle midi input
    if msg := midi.receive():
        if msg.type == tmidi.NOTE_ON and msg.velocity > 0:
            print("note on", msg)
            pressed_notes.append(msg.note)
        elif msg.type == tmidi.NOTE_OFF or (
            msg.type == tmidi.NOTE_ON and msg.velocity == 0
        ):
            if msg.note in pressed_notes:
                midi.send(msg)  # send the note off
                pressed_notes.remove(msg.note)
                note_i = 0

    # do midi output
    if len(pressed_notes) == 0:
        continue

    now = time.monotonic()
    if now - last_note_time >= note_time:
        last_note_time = now
        note_on = tmidi.Message(tmidi.NOTE_ON, pressed_notes[note_i], 127)
        print("arp note_on: ", note_on)
        midi.send(note_on)
        gate_time = note_time * gate_percent

    if gate_time > 0 and now - last_note_time >= gate_time:
        gate_time = 0
        note_off = tmidi.Message(tmidi.NOTE_OFF, pressed_notes[note_i], 127)
        print("arp note_off:", note_off)
        midi.send(note_off)
        note_i = (note_i + 1) % len(pressed_notes)
