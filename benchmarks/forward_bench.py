# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
CPU cost of forwarding each received message to an out port, for tmidi
(viper and Python parsers) and adafruit_midi. No MIDI cable involved, so
the results aren't capped by the 31250 baud wire.

Copy this repo's tmidi/ and adafruit_midi/ to CIRCUITPY/lib/, then this
file as code.py.
"""

import gc
import time
from io import BytesIO

import adafruit_midi
import microcontroller
from adafruit_midi.control_change import ControlChange  # noqa: F401
from adafruit_midi.note_on import NoteOn  # noqa: F401
from adafruit_midi.pitch_bend import PitchBend  # noqa: F401

import tmidi

N = 3000
REPEATS = 3
DATA = bytes([0x90, 60, 100, 0xB0, 74, 64, 0xE0, 0x00, 0x40]) * (N // 3)
TYPES = (tmidi.NOTE_ON, tmidi.CC, tmidi.PITCH_BEND)


class BufPort:
    """read() for adafruit_midi, readinto() for tmidi."""

    def __init__(self, data):
        self._data = memoryview(data)
        self._pos = 0

    def read(self, numbytes=1):
        end = min(self._pos + numbytes, len(self._data))
        chunk = bytes(self._data[self._pos : end])
        self._pos = end
        return chunk

    def readinto(self, buf, numbytes=1):
        n = min(numbytes, len(self._data) - self._pos)
        if n <= 0:
            return 0
        buf[:n] = self._data[self._pos : self._pos + n]
        self._pos += n
        return n


def sink():
    # pre-sized, as growing a BytesIO a few bytes at a time costs more than the rest
    port = BytesIO()
    port.write(bytes(len(DATA)))
    port.seek(0)
    return port


def tmidi_poll(turbo):
    """What examples/tmidi_midi_interface does."""
    out_port = sink()
    midi = tmidi.MIDI(midi_in=BufPort(DATA), turbo=turbo)
    out = bytearray(3)

    def forwarder(mtype):
        def forward(channel, data0, data1):
            out[0] = mtype | channel
            out[1] = data0
            out[2] = data1
            out_port.write(out, 3)

        return forward

    for mtype in TYPES:
        midi.on(mtype, forwarder(mtype))
    return midi.poll, out_port


def tmidi_receive(turbo):
    out_port = sink()
    midi = tmidi.MIDI(midi_in=BufPort(DATA), midi_out=out_port, turbo=turbo)

    def step():
        msg = midi.receive()
        if msg is None:
            return 0
        midi.send(msg)
        return 1

    return step, out_port


def adafruit():
    out_port = sink()
    midi = adafruit_midi.MIDI(midi_in=BufPort(DATA), midi_out=out_port)

    def step():
        msg = midi.receive()
        if msg is None:
            return 0
        midi.send(msg, channel=msg.channel)
        return 1

    return step, out_port


def run(label, make, *args):
    best = None
    for _ in range(REPEATS):
        step, port = make(*args)
        gc.collect()
        count = 0
        t0 = time.monotonic_ns()
        while n := step():
            count += n
        us = (time.monotonic_ns() - t0) / 1000 / count
        best = us if best is None else min(best, us)
        assert port.getvalue() == DATA, label

    # allocation, on a short run so the heap can't fill with gc off
    step, port = make(*args)
    gc.collect()
    gc.disable()
    alloc = gc.mem_alloc()
    count = 0
    for _ in range(100):
        count += step()
    alloc = (gc.mem_alloc() - alloc) / count
    gc.enable()
    print("  %-28s %6.1f µs/msg  %4d bytes/msg" % (label, best, alloc))


print(
    "forward %d msgs, best of %d, %d MHz"
    % (N, REPEATS, microcontroller.cpu.frequency // 1_000_000)
)
run("tmidi viper poll+write", tmidi_poll, True)
run("tmidi Python poll+write", tmidi_poll, False)
run("tmidi viper receive+send", tmidi_receive, True)
run("tmidi Python receive+send", tmidi_receive, False)
run("adafruit_midi receive+send", adafruit)
