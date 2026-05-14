# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
Synthetic benchmark comparing tmidi vs adafruit_midi receive() performance.
Run on a CircuitPython board (tested on RP2350 Pico 2).

Copy both tmidi.py and adafruit_midi/ to the board's lib/ folder, then run this
script. Each library is tested against the same pre-loaded byte buffer so results
are directly comparable. Results print as µs/msg and net heap change.

Example output (RP2350 Pico 2):
  tmidi          : 6000 msgs, 160 µs/msg, heap: -32 bytes
  adafruit_midi  : 6000 msgs, 385 µs/msg, heap: -32 bytes
  tmidi is 2.4x faster than adafruit_midi
"""

import gc
import time

# One repetition of every message type to test. Add/remove rows freely.
# fmt: off
_PATTERN = bytes([
    0x90, 60, 100,      # NOTE_ON
    0x80, 60,   0,      # NOTE_OFF
    0xB0, 74,  64,      # CC
    0xD0, 64,           # CHANNEL_PRESSURE
    0xC0, 42,           # PROGRAM_CHANGE
    0xE0, 0x00, 0x40,   # PITCH_BEND center
])
# fmt: on
_MSGS_PER_PATTERN = 6  # update this when adding/removing rows above
REPS = 1000
BENCH_BYTES = _PATTERN * REPS


class BufPort:
    """Fake MIDI port backed by a pre-loaded byte buffer.
    Implements both read() (adafruit_midi) and readinto() (tmidi).
    """

    def __init__(self, data):
        self._data = memoryview(data)
        self._pos = 0

    def read(self, numbytes=1):
        if self._pos >= len(self._data):
            return b""
        end = min(self._pos + numbytes, len(self._data))
        chunk = bytes(self._data[self._pos : end])
        self._pos = end
        return chunk

    def readinto(self, buf, numbytes=1):
        if self._pos >= len(self._data):
            return 0
        buf[0] = self._data[self._pos]
        self._pos += 1
        return 1


def run_benchmark(midi, label):
    gc.collect()
    free_before = gc.mem_free()
    t0 = time.monotonic_ns()
    count = 0
    while True:
        if midi.receive() is None:
            break
        count += 1
    elapsed_us = (time.monotonic_ns() - t0) // 1000
    gc.collect()
    heap_delta = gc.mem_free() - free_before
    us_per_msg = elapsed_us // count if count else 0
    print(f"  {label:<15}: {count} msgs, {us_per_msg} µs/msg, heap: {heap_delta} bytes")
    return us_per_msg


print("tmidi vs adafruit_midi synthetic benchmark")
print("=" * 50)

results = {}

try:
    import tmidi
    # import tmidi_old as tmidi

    midi = tmidi.MIDI(midi_in=BufPort(BENCH_BYTES))
    results["tmidi"] = run_benchmark(midi, "tmidi")
except ImportError:
    print("  tmidi: not installed")

try:
    import adafruit_midi
    from adafruit_midi.control_change import ControlChange  # noqa: F401
    from adafruit_midi.note_on import NoteOn  # noqa: F401
    from adafruit_midi.note_off import NoteOff  # noqa: F401
    from adafruit_midi.pitch_bend import PitchBend  # noqa: F401
    from adafruit_midi.channel_pressure import ChannelPressure  # noqa: F401
    from adafruit_midi.program_change import ProgramChange  # noqa: F401

    midi = adafruit_midi.MIDI(midi_in=BufPort(BENCH_BYTES), in_channel=0)
    results["adafruit_midi"] = run_benchmark(midi, "adafruit_midi")
except ImportError:
    print("  adafruit_midi: not installed")

if "tmidi" in results and "adafruit_midi" in results:
    ratio = results["adafruit_midi"] / results["tmidi"]
    print(f"\ntmidi is {ratio:.1f}x faster than adafruit_midi")
