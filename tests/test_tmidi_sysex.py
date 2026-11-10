# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
# SPDX-License-Identifier: MIT

import tmidi


class PortStub:
    def __init__(self, data):
        self.data = data

    def readinto(self, buf, numbytes=1):
        bytes_read = 0
        for n in range(numbytes):
            try:
                value = next(self.data)
                buf[n] = value
                bytes_read += 1
            except StopIteration:
                break
        return bytes_read


def test_sysex_empty():
    # Bare F0 F7 with no payload
    port = PortStub(iter([0xF0, 0xF7]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.SYSEX
    assert midi_in.error_count == 0


def test_sysex_with_payload():
    # Standard device inquiry SysEx
    port = PortStub(iter([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.SYSEX
    assert midi_in.error_count == 0


def test_sysex_long_payload():
    # 64-byte payload — parser must consume all of it
    payload = list(range(64))  # 0x00–0x3F, all valid data bytes
    port = PortStub(iter([0xF0] + payload + [0xF7]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.SYSEX
    assert midi_in.error_count == 0


def test_sysex_consecutive():
    # Two SysEx messages back to back, then a CC — all three must parse cleanly
    sysex1 = [0xF0, 0x41, 0x10, 0x42, 0xF7]
    sysex2 = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    cc = [0xB2, 74, 64]
    port = PortStub(iter(sysex1 + sysex2 + cc))
    midi_in = tmidi.MIDI(midi_in=port)

    msg1 = midi_in.receive()
    assert msg1 is not None and msg1.type == tmidi.SYSEX

    msg2 = midi_in.receive()
    assert msg2 is not None and msg2.type == tmidi.SYSEX

    msg3 = midi_in.receive()
    assert msg3 is not None
    assert msg3.type == tmidi.CC
    assert msg3.channel == 2
    assert msg3.data0 == 74
    assert msg3.data1 == 64
    assert midi_in.error_count == 0


def test_sysex_buffer_captures_payload():
    payload = [0x7E, 0x7F, 0x06, 0x01]
    port = PortStub(iter([0xF0] + payload + [0xF7]))
    sysex_buf = bytearray(16)
    midi_in = tmidi.MIDI(midi_in=port, sysex_buffer=sysex_buf)
    msg = midi_in.receive()
    assert msg is not None
    assert msg.type == tmidi.SYSEX
    assert msg.data0 == len(payload)
    assert list(sysex_buf[: msg.data0]) == payload
    assert midi_in.error_count == 0


def test_sysex_buffer_truncates_when_full():
    # Payload longer than buffer — stream must stay in sync, no hang.
    payload = list(range(32))
    port = PortStub(iter([0xF0] + payload + [0xF7, 0x90, 60, 100]))
    sysex_buf = bytearray(8)
    midi_in = tmidi.MIDI(midi_in=port, sysex_buffer=sysex_buf)
    msg1 = midi_in.receive()
    assert msg1 is not None and msg1.type == tmidi.SYSEX
    assert msg1.data0 == 8  # buffer filled to capacity
    assert list(sysex_buf) == payload[:8]
    msg2 = midi_in.receive()
    assert msg2 is not None and msg2.type == tmidi.NOTE_ON
    assert midi_in.error_count == 0


def test_sysex_no_buffer_data0_is_zero():
    port = PortStub(iter([0xF0, 0x7E, 0x7F, 0xF7]))
    midi_in = tmidi.MIDI(midi_in=port)
    msg = midi_in.receive()
    assert msg is not None and msg.type == tmidi.SYSEX
    assert msg.data0 == 0


def test_sysex_does_not_set_running_status():
    # SysEx is a system message and must not update running status.
    # A data byte after SysEx with no new status should be an error,
    # not silently reuse a pre-SysEx running status.
    note_on = [0x90, 60, 100]
    sysex = [0xF0, 0x01, 0x02, 0xF7]
    bare_data = [0x40]  # data byte with no status — invalid on its own
    port = PortStub(iter(note_on + sysex + bare_data))
    midi_in = tmidi.MIDI(midi_in=port, enable_running_status=True)

    msg1 = midi_in.receive()
    assert msg1 is not None and msg1.type == tmidi.NOTE_ON  # sets running status

    msg2 = midi_in.receive()
    assert msg2 is not None and msg2.type == tmidi.SYSEX  # must NOT update running status

    msg3 = midi_in.receive()
    # bare_data after SysEx: running status from before SysEx should NOT apply
    assert msg3 is None
    assert midi_in.error_count == 1
