# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT
"""Replay MIDI bytes captured from real hardware through both parsers."""

import random
from pathlib import Path

import tmidi
from tests.test_kernel_model import load_kernel

CAPTURE = Path(__file__).parent / "data" / "rk006_capture.txt"


def load_capture():
    wire = bytearray()
    messages = []
    section = None
    for line in CAPTURE.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line
        elif section == "[wire]":
            wire.extend(bytes.fromhex(line))
        else:
            t, ch, d0, d1 = line.split()
            messages.append((int(t, 16), int(ch), int(d0), int(d1)))
    return bytes(wire), messages


class SplitPort:
    """Hands out the capture in the given chunk sizes, like a UART would"""

    def __init__(self, data, sizes):
        self.data = data
        self.sizes = sizes

    def readinto(self, buf, numbytes=1):
        n = min(next(self.sizes), numbytes, len(self.data))
        buf[:n] = self.data[:n]
        self.data = self.data[n:]
        return n


def parse(wire, sizes, parser):
    midi = tmidi.MIDI(SplitPort(wire, sizes), sysex_buffer=bytearray(128), turbo=False)
    midi._parse = parser
    got = []
    while (msg := midi.receive()) is not None:
        got.append((msg.type, msg.channel, msg.data0, msg.data1))
    return got, midi.error_count


def chunks(fixed=None, seed=0):
    rng = random.Random(seed)
    while True:
        yield fixed or rng.randrange(1, 65)


def test_capture_parses_both_engines():
    wire, messages = load_capture()
    for parser in (tmidi._parse_py, load_kernel().parse):
        for sizes in (chunks(1), chunks(3), chunks(64), chunks(seed=5)):
            assert parse(wire, sizes, parser) == (messages, 0)
