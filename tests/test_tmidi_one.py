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

    def write(self, buf):
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
