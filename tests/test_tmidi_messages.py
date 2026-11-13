# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT


import time

import tmidi


class PortStub:
    def __init__(self, data):
        self.data = data
        self.expected = None

    def write(self, buf, nbytes):
        # real ports write only nbytes, and send() hands over a scratch buffer
        assert self.expected == list(buf[:nbytes])


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


def test_send_shorter_after_longer():
    # the scratch buffer still holds the note on's third byte
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    port.expected = [0x90, 60, 100]
    midi_out.send(tmidi.Message(tmidi.NOTE_ON, 60, 100))
    port.expected = [0xC2, 7]
    midi_out.send(tmidi.Message(tmidi.PROGRAM_CHANGE, 7, channel=2))
    port.expected = [0xF8]
    midi_out.send(tmidi.Message(tmidi.CLOCK))


def test_bytes_after_send():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    port.expected = [0x90, 60, 100]
    midi_out.send(tmidi.Message(tmidi.NOTE_ON, 60, 100))
    assert bytes(tmidi.Message(tmidi.CHANNEL_PRESSURE, 9).__bytes__()) == b"\xd0\x09"


def test_write_sysex():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    port.expected = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    midi_out.write(bytes(port.expected))


def test_write_n():
    port = PortStub(iter([]))
    midi_out = tmidi.MIDI(midi_out=port)

    buf = bytearray([0x90, 60, 100, 0x80, 60, 0])
    port.expected = [0x90, 60, 100]
    midi_out.write(buf, 3)


class ChunkPort:
    """Takes at most `take` bytes per write, like usb_midi's USB buffer."""

    def __init__(self, take, total=None):
        self.take = take
        self.total = total  # stop taking bytes after this many
        self.out = bytearray()

    def write(self, buf, nbytes):
        n = min(nbytes, self.take)
        if self.total is not None:
            n = min(n, self.total - len(self.out))
        self.out += bytes(buf[:n])
        return n


SYSEX = bytes([0xF0, 0x7D] + [i & 0x7F for i in range(298)] + [0xF7])


def test_write_partial():
    port = ChunkPort(144)
    midi_out = tmidi.MIDI(midi_out=port)

    assert midi_out.write(SYSEX) is True
    assert port.out == SYSEX


def test_write_n_partial():
    port = ChunkPort(7)
    midi_out = tmidi.MIDI(midi_out=port)

    assert midi_out.write(bytearray(SYSEX) + b"\x00" * 10, len(SYSEX)) is True
    assert port.out == SYSEX


def test_write_stalled():
    # usb_midi takes nothing while no app has the port open
    port = ChunkPort(144, total=0)
    midi_out = tmidi.MIDI(midi_out=port)

    t0 = time.monotonic()
    assert midi_out.write(SYSEX) is False
    assert time.monotonic() - t0 < 0.5
    assert port.out == b""


def test_write_stalls_partway():
    port = ChunkPort(144, total=200)
    midi_out = tmidi.MIDI(midi_out=port)

    assert midi_out.write(SYSEX) is False
    assert port.out == SYSEX[:200]


def test_send_batch_partial():
    port = ChunkPort(10)
    midi_out = tmidi.MIDI(midi_out=port)

    msgs = [tmidi.Message(tmidi.NOTE_ON, n, 100) for n in range(60)]
    midi_out.send(msgs)
    assert port.out == b"".join(bytes([0x90, n, 100]) for n in range(60))
