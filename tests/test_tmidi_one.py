# SPDX-FileCopyrightText: Copyright (c) 2019 Alethea Flowers for Winterbloom
# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
# SPDX-License-Identifier: MIT


import tmidi


class PortStub:
    def __init__(self, data):
        self.data = data

    def read(self, numbytes=None):
        if numbytes is None:
            numbytes = len(self.data)
        buf = bytearray(numbytes)
        self.readinto(buf, numbytes)
        return buf

    def readinto(self, buf, numbytes=1):
        bytes_read = 0
        for n in range(numbytes):
            try:
                value = next(self.data)
                if isinstance(value, Exception):
                    raise value

                buf[n] = value
                bytes_read += 1
            except StopIteration:
                break

        return bytes_read

    def write(self, buf, n):
        pass


def test_construction():
    port = PortStub(iter([0x01]))
    midi_in = tmidi.MIDI(midi_in=port)

    assert port is not None
    assert midi_in is not None


def test_midi_in_empty():
    port = PortStub(iter([]))
    midi_in = tmidi.MIDI(port)

    msg = midi_in.receive()

    assert msg is None


def test_midi_in_invalid_data():
    # A port with non-status leading bytes
    port = PortStub(iter([0x01]))
    midi_in = tmidi.MIDI(midi_in=port)

    msg = midi_in.receive()

    assert msg is None
    assert midi_in.error_count == 1


def test_note_on_receive():
    port = PortStub(iter([0x90, 60, 100]))
    midi_in = tmidi.MIDI(midi_in=port)

    msg = midi_in.receive()

    assert msg is not None
    assert msg.type == tmidi.NOTE_ON
    assert msg.channel == 0
    assert msg.note == 60
    assert msg.velocity == 100
    assert midi_in.error_count == 0


def test_note_on_receive_roundtrip():
    port = PortStub(iter([0x93, 60, 100]))
    midi_in = tmidi.MIDI(midi_in=port)

    msg = midi_in.receive()

    assert msg is not None
    assert bytes(msg.__bytes__()) == bytes([0x93, 60, 100])


def test_pitch_bend_receive():
    # Center: wire [0xE0, 0x00, 0x40] → pitch_bend = 0
    port = PortStub(iter([0xE0, 0x00, 0x40]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.PITCH_BEND
    assert msg.pitch_bend == 0
    assert list(msg.__bytes__()) == [0xE0, 0x00, 0x40]


def test_pitch_bend_full_down():
    # Full down: wire [0xE0, 0x00, 0x00] → pitch_bend = -8192
    # data1=0x00 must not trigger the __init__ user-API special case
    port = PortStub(iter([0xE0, 0x00, 0x00]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.PITCH_BEND
    assert msg.pitch_bend == -8192
    assert list(msg.__bytes__()) == [0xE0, 0x00, 0x00]


def test_pitch_bend_full_up():
    # Full up: wire [0xE0, 0x7F, 0x7F] → pitch_bend = 8191
    port = PortStub(iter([0xE0, 0x7F, 0x7F]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.PITCH_BEND
    assert msg.pitch_bend == 8191
    assert list(msg.__bytes__()) == [0xE0, 0x7F, 0x7F]


def test_data_byte_corruption():
    # Status byte appearing in data position should trigger error
    port = PortStub(iter([0x90, 0x90, 60]))
    midi_in = tmidi.MIDI(midi_in=port)

    msg = midi_in.receive()

    assert msg is None
    assert midi_in.error_count == 1


def test_sysex_receive_no_desync():
    # SysEx followed by Note On: parser must consume the SysEx payload
    # so the Note On is parsed cleanly with no error count.
    sysex = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    note_on = [0x91, 60, 127]
    port = PortStub(iter(sysex + note_on))
    midi_in = tmidi.MIDI(midi_in=port)

    msg1 = midi_in.receive()
    assert msg1 is not None
    assert msg1.type == tmidi.SYSEX

    msg2 = midi_in.receive()
    assert msg2 is not None
    assert msg2.type == tmidi.NOTE_ON
    assert msg2.channel == 1
    assert msg2.note == 60
    assert msg2.velocity == 127
    assert midi_in.error_count == 0
