# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT


import tmidi


class PortStub:
    def __init__(self, data):
        self.data = data
        self.expected = None

    def write(self, buf, nbytes):
        assert self.expected == list(buf)


def test_message_note_on():
    msg = tmidi.Message(tmidi.NOTE_ON, 64, 123)
    assert str(msg) == "Message(NoteOn ch:0 64 123)"


def test_message_program_change():
    msg = tmidi.Message(tmidi.PROGRAM_CHANGE, 120, channel=11)
    assert str(msg) == "Message(ProgramChange ch:11 120)"


def test_message_note_on_send():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    msg = tmidi.Message(tmidi.NOTE_ON, 64, 123)
    port.expected = [0x90, 64, 123]
    midi_out.send(msg)

    msg = tmidi.Message(tmidi.NOTE_ON, 32, 111, channel=3)
    port.expected = [0x93, 32, 111]
    midi_out.send(msg)


def test_message_program_change_send():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    msg = tmidi.Message(tmidi.PROGRAM_CHANGE, 33)
    port.expected = [0xC0, 33]
    midi_out.send(msg)


def test_send_channel_zero():
    # channel=0 must not be treated as falsy and ignored
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    msg = tmidi.Message(tmidi.NOTE_ON, 60, 100, channel=5)
    port.expected = [0x90, 60, 100]  # channel overridden to 0
    midi_out.send(msg, channel=0)


def test_send_clock():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    msg = tmidi.Message(tmidi.CLOCK)
    port.expected = [0xF8]
    midi_out.send(msg)


def test_send_batch():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    msgs = [
        tmidi.Message(tmidi.NOTE_ON, 60, 100),
        tmidi.Message(tmidi.NOTE_OFF, 60, 0),
    ]
    port.expected = [0x90, 60, 100, 0x80, 60, 0]
    midi_out.send(msgs)
