# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

import tmidi


class ChunkPort:
    """Port returning one pre-set chunk per readinto call, b"" when nothing arrived"""

    def __init__(self, *chunks):
        self.chunks = list(chunks)

    def readinto(self, buf, numbytes=1):
        if not self.chunks:
            return 0
        chunk = self.chunks.pop(0)
        assert len(chunk) <= numbytes
        buf[: len(chunk)] = chunk
        return len(chunk)


class UartPort(ChunkPort):
    in_waiting = 0

    def readinto(self, buf, numbytes=1):
        assert numbytes <= self.in_waiting
        return super().readinto(buf, numbytes)


class OneArgPort:
    """readinto like adafruit_usb_host_midi: no numbytes, and sizes buf to the data"""

    def __init__(self, data):
        self.data = list(data)

    def readinto(self, buf):
        b = bytes(self.data[: len(buf)])
        del self.data[: len(buf)]
        if b:
            buf[:] = b
        return len(b)


def test_one_arg_readinto_port():
    midi = tmidi.MIDI(OneArgPort([0x90, 60, 100, 0xB0, 1, 2]))
    assert midi.receive().note == 60
    assert midi.receive().type == tmidi.CC
    assert midi.receive() is None
    assert len(midi._buf) == tmidi._READ_SIZE


def recorder(calls, name):
    def func(channel, data0, data1):
        calls.append((name, channel, data0, data1))

    return func


def test_callbacks_dispatch_by_type():
    midi = tmidi.MIDI(ChunkPort(bytes([0x91, 60, 100, 0xB2, 74, 64, 0xC3, 5, 0xF8])))
    calls = []
    midi.on(tmidi.NOTE_ON, recorder(calls, "on"))
    midi.on(tmidi.CC, recorder(calls, "cc"))
    midi.on(tmidi.PROGRAM_CHANGE, recorder(calls, "pc"))
    midi.on(tmidi.CLOCK, recorder(calls, "clock"))
    assert midi.poll() == 4
    assert calls == [
        ("on", 1, 60, 100),
        ("cc", 2, 74, 64),
        ("pc", 3, 5, 0),
        ("clock", 0, 0, 0),
    ]


def test_message_without_callback_is_consumed():
    midi = tmidi.MIDI(ChunkPort(bytes([0x80, 60, 0, 0x90, 61, 1])))
    calls = []
    midi.on(tmidi.NOTE_ON, recorder(calls, "on"))
    assert midi.poll() == 2
    assert calls == [("on", 0, 61, 1)]


def test_unregister():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90, 60, 100])))
    calls = []
    midi.on(tmidi.NOTE_ON, recorder(calls, "on"))
    midi.on(tmidi.NOTE_ON, None)
    midi.on(tmidi.CC, None)
    assert midi.poll() == 1
    assert not calls


def test_poll_limit_then_mix_with_receive():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90, 1, 1, 0x90, 2, 2, 0x90, 3, 3])))
    calls = []
    midi.on(tmidi.NOTE_ON, recorder(calls, "on"))
    assert midi.poll(limit=1) == 1
    assert calls == [("on", 0, 1, 1)]
    assert midi.receive().note == 2
    assert midi.poll() == 1
    assert calls[-1] == ("on", 0, 3, 3)


def test_sysex_callback_gets_length():
    sysex_buf = bytearray(16)
    midi = tmidi.MIDI(ChunkPort(bytes([0xF0, 1, 2, 3, 0xF7])), sysex_buffer=sysex_buf)
    calls = []
    midi.on(tmidi.SYSEX, recorder(calls, "sysex"))
    assert midi.poll() == 1
    assert calls == [("sysex", 0, 3, 0)]
    assert list(sysex_buf[:3]) == [1, 2, 3]


def test_partial_message_resumes_on_later_receive():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90]), b"", bytes([60]), b"", bytes([100])))
    assert midi.receive() is None
    assert midi.receive() is None
    msg = midi.receive()
    assert (msg.type, msg.note, msg.velocity) == (tmidi.NOTE_ON, 60, 100)
    assert midi.error_count == 0


def test_realtime_inside_message():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90, 0xF8, 60, 0xFA, 100])))
    assert midi.receive().type == tmidi.CLOCK
    assert midi.receive().type == tmidi.START
    assert midi.receive().note == 60
    assert midi.error_count == 0


def test_realtime_inside_sysex_not_in_payload():
    sysex_buf = bytearray(8)
    port = ChunkPort(bytes([0xF0, 1, 0xF8, 2, 0xF7]))
    midi = tmidi.MIDI(port, sysex_buffer=sysex_buf)
    assert midi.receive().type == tmidi.CLOCK
    msg = midi.receive()
    assert (msg.type, msg.data0) == (tmidi.SYSEX, 2)
    assert list(sysex_buf[:2]) == [1, 2]


def test_status_inside_sysex_abandons_it():
    midi = tmidi.MIDI(ChunkPort(bytes([0xF0, 1, 0x90, 60, 100])))
    msg = midi.receive()
    assert (msg.type, msg.note) == (tmidi.NOTE_ON, 60)
    assert midi.error_count == 1


def test_status_in_data_position_starts_new_message():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90, 60, 0x91, 61, 100])))
    msg = midi.receive()
    assert (msg.channel, msg.note, msg.velocity) == (1, 61, 100)
    assert midi.error_count == 1


def test_running_status_keeps_first_data_byte():
    port = ChunkPort(bytes([0x90, 60, 100, 61, 101]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    assert midi.receive().note == 60
    msg = midi.receive()
    assert (msg.type, msg.note, msg.velocity) == (tmidi.NOTE_ON, 61, 101)
    assert midi.error_count == 0


def test_running_status_off_is_error():
    midi = tmidi.MIDI(ChunkPort(bytes([0x90, 60, 100, 61, 101])))
    assert midi.receive().note == 60
    assert midi.receive() is None
    assert midi.error_count == 2


def test_system_common_cancels_running_status():
    port = ChunkPort(bytes([0x90, 60, 100, 0xF6, 61]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    assert midi.receive().note == 60
    assert midi.receive().type == tmidi.TUNE_REQUEST
    assert midi.receive() is None
    assert midi.error_count == 1


def test_realtime_keeps_running_status():
    port = ChunkPort(bytes([0x90, 60, 100, 0xF8, 61, 0xFE, 101, 62, 102]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    got = []
    while msg := midi.receive():
        got.append((msg.type, msg.data0, msg.data1))
    assert got == [
        (tmidi.NOTE_ON, 60, 100),
        (tmidi.CLOCK, 0, 0),
        (tmidi.ACTIVE_SENSING, 0, 0),
        (tmidi.NOTE_ON, 61, 101),
        (tmidi.NOTE_ON, 62, 102),
    ]
    assert midi.error_count == 0


def test_running_status_one_data_byte():
    port = ChunkPort(bytes([0xC3, 5, 6, 0xD4, 77, 78]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    got = []
    while msg := midi.receive():
        got.append((msg.type, msg.channel, msg.data0))
    assert got == [
        (tmidi.PROGRAM_CHANGE, 3, 5),
        (tmidi.PROGRAM_CHANGE, 3, 6),
        (tmidi.CHANNEL_PRESSURE, 4, 77),
        (tmidi.CHANNEL_PRESSURE, 4, 78),
    ]
    assert midi.error_count == 0


def test_running_status_across_reads():
    port = ChunkPort(bytes([0xB0, 1, 2, 3]), b"", bytes([4, 5]), bytes([6]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    got = []
    for _ in range(6):
        msg = midi.receive()
        if msg:
            got.append((msg.data0, msg.data1))
    assert got == [(1, 2), (3, 4), (5, 6)]
    assert midi.error_count == 0


def test_running_status_poll():
    port = ChunkPort(bytes([0x91, 60, 100, 61, 0, 0xB2, 74, 64, 75, 65]))
    midi = tmidi.MIDI(port, enable_running_status=True)
    calls = []
    midi.on(tmidi.NOTE_ON, recorder(calls, "on"))
    midi.on(tmidi.CC, recorder(calls, "cc"))
    assert midi.poll() == 4
    assert calls == [
        ("on", 1, 60, 100),
        ("on", 1, 61, 0),
        ("cc", 2, 74, 64),
        ("cc", 2, 75, 65),
    ]
    assert midi.error_count == 0


def test_message_straddling_read_size():
    data = bytes([0xB0, 1, 2] * 22)
    midi = tmidi.MIDI(ChunkPort(data[:64], data[64:]))
    count = 0
    while midi.receive():
        count += 1
    assert count == 22
    assert midi.error_count == 0


def test_uart_reads_only_in_waiting():
    port = UartPort(bytes([0x90, 60, 100]))
    midi = tmidi.MIDI(port)
    assert midi.receive() is None
    port.in_waiting = 3
    assert midi.receive().note == 60
