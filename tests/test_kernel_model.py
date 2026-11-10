# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT
"""Run src/tmidi_turbo.py under CPython and check it against the Python parser.

This covers the kernel's logic only. The compiled kernel needs a board.
"""

import random
import types
from array import array
from pathlib import Path

import micropython

import tmidi

ROOT = Path(__file__).resolve().parents[1]
STATUS_BYTES = [
    0x80, 0x93, 0xA0, 0xB5, 0xC0, 0xD7, 0xE0, 0xF0, 0xF2, 0xF3, 0xF5, 0xF6, 0xF7, 0xF8, 0xFE,
]  # fmt: skip


def load_kernel():
    micropython.viper = lambda function: function
    model = types.ModuleType("tmidi_kernel_model")
    model.ptr8 = model.ptr16 = object
    source = (ROOT / "src" / "tmidi_turbo.py").read_text()
    exec(compile(source, "tmidi_turbo.py", "exec"), model.__dict__)
    return model


def run(parse, stream, splits, running):
    buf = bytearray(tmidi._READ_SIZE)
    sx = bytearray(8)
    st = array("H", [0] * tmidi._ST_SIZE)
    st[tmidi._ST_SX_CAP] = len(sx)
    st[tmidi._ST_RUNNING_ON] = running
    results = []
    pos = 0
    for size in splits:
        chunk = stream[pos : pos + size]
        pos += size
        buf[: len(chunk)] = chunk
        st[tmidi._ST_RD] = 0
        st[tmidi._ST_WR] = len(chunk)
        while r := parse(buf, st, sx):
            results.append(r)
    return results, list(st), bytes(sx)


def test_kernel_slots_match_python():
    kernel = load_kernel()
    for name in dir(tmidi):
        if name.startswith(("_ST_", "_NEED_", "_B_")) and name != "_ST_SIZE":
            assert getattr(kernel, name) == getattr(tmidi, name)


def test_fuzz_kernel_matches_python():
    kernel = load_kernel()
    rng = random.Random(31)
    for _ in range(3000):
        stream = bytes(
            rng.choice(STATUS_BYTES) if rng.random() < 0.3 else rng.randrange(128)
            for _ in range(rng.randrange(1, 200))
        )
        splits = [rng.randrange(1, 65) for _ in range(len(stream))]
        running = rng.randrange(2)
        got = run(kernel.parse, stream, splits, running)
        assert got == run(tmidi._parse_py, stream, splits, running)
