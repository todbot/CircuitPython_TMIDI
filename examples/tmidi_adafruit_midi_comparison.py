# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
Synthetic benchmark comparing tmidi vs adafruit_midi receive() performance.
Run on a CircuitPython board (tested on RP2350 Pico 2).

Copy both tmidi.py and adafruit_midi/ to the board's lib/ folder, then run this
script. Each library is tested against the same pre-loaded byte buffer so results
are directly comparable. Results print as µs/msg and net heap change.

Prints µs/msg for receive() and poll(), on the viper parser if it loaded and on
the pure Python one.

Example output (RP2040 Pico @ 125 MHz, CircuitPython 11.0.0-alpha.2,
tmidi_kernel.armv6m.mpy and adafruit_midi as .mpy):
  engine: viper
  tmidi (viper)      : 20000 msgs, 206 µs/msg, heap: -80 bytes
  tmidi (Python)     : 20000 msgs, 301 µs/msg, heap: -32 bytes
  tmidi poll (viper) : 20000 msgs, 51 µs/msg, heap: -32 bytes
  tmidi poll (Python): 20000 msgs, 134 µs/msg, heap: -32 bytes
  adafruit_midi      : 20000 msgs, 1063 µs/msg, heap: -32 bytes
  tmidi (viper) is 5.2x faster than adafruit_midi
  tmidi (Python) is 3.5x faster than adafruit_midi
"""

import gc
import time

# One repetition of every message type to test. Add/remove rows freely.
# fmt: off
_PATTERN = bytes([
    0x90, 60, 100,      # NOTE_ON
    0xF8,               # CLOCK
    0x90, 64, 100,      # NOTE_ON
    0xB0, 74,  64,      # CC
    0x80, 60,   0,      # NOTE_OFF
    0xF8,               # CLOCK
    0x90, 67, 100,      # NOTE_ON
    0xD0, 64,           # CHANNEL_PRESSURE
    0x80, 64,   0,      # NOTE_OFF
    0xC0, 42,           # PROGRAM_CHANGE
    0x90, 72, 100,      # NOTE_ON
    0xFA,               # START
    0x80, 67,   0,      # NOTE_OFF
    0xE0, 0x00, 0x40,   # PITCH_BEND center
    0x90, 76, 100,      # NOTE_ON
    0xFC,               # STOP
    0x80, 72,   0,      # NOTE_OFF
    0x90, 79, 100,      # NOTE_ON
    0x80, 76,   0,      # NOTE_OFF
    0x80, 79,   0,      # NOTE_OFF
])
# fmt: on
_MSGS_PER_PATTERN = 20  # update this when adding/removing rows above
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
        n = min(numbytes, len(self._data) - self._pos)
        if n <= 0:
            return 0
        buf[:n] = self._data[self._pos : self._pos + n]
        self._pos += n
        return n


def run_benchmark(midi, label, poll=False):
    gc.collect()
    free_before = gc.mem_free()
    t0 = time.monotonic_ns()
    count = 0
    while True:
        if poll:
            n = midi.poll()
            if not n:
                break
            count += n
        else:
            if midi.receive() is None:
                break
            count += 1
    elapsed_us = (time.monotonic_ns() - t0) // 1000
    gc.collect()
    heap_delta = gc.mem_free() - free_before
    us_per_msg = elapsed_us // count if count else 0
    print(f"  {label:<19}: {count} msgs, {us_per_msg} µs/msg, heap: {heap_delta} bytes")
    return us_per_msg


print("tmidi vs adafruit_midi synthetic benchmark")
print("=" * 50)

results = {}

try:
    import tmidi
    # import tmidi_old as tmidi

    print("  engine:", tmidi.ENGINE)
    midi = tmidi.MIDI(midi_in=BufPort(BENCH_BYTES))
    results["tmidi"] = run_benchmark(midi, f"tmidi ({tmidi.ENGINE})")
    midi = tmidi.MIDI(midi_in=BufPort(BENCH_BYTES), turbo=False)
    results["tmidi_py"] = run_benchmark(midi, "tmidi (Python)")

    def _on_msg(channel, data0, data1):
        pass

    for turbo in (True, False):
        midi = tmidi.MIDI(midi_in=BufPort(BENCH_BYTES), turbo=turbo)
        for mtype in (tmidi.NOTE_ON, tmidi.NOTE_OFF, tmidi.CC, tmidi.CLOCK):
            midi.on(mtype, _on_msg)
        engine = tmidi.ENGINE if turbo else "Python"
        run_benchmark(midi, f"tmidi poll ({engine})", poll=True)
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
    from adafruit_midi.timing_clock import TimingClock  # noqa: F401
    from adafruit_midi.start import Start  # noqa: F401
    from adafruit_midi.stop import Stop  # noqa: F401

    midi = adafruit_midi.MIDI(midi_in=BufPort(BENCH_BYTES), in_channel=0)
    results["adafruit_midi"] = run_benchmark(midi, "adafruit_midi")
except ImportError:
    print("  adafruit_midi: not installed")

if "tmidi" in results and "adafruit_midi" in results:
    ratio = results["adafruit_midi"] / results["tmidi"]
    print(f"tmidi ({tmidi.ENGINE}) is {ratio:.1f}x faster than adafruit_midi")
    if tmidi.ENGINE != "Python":
        ratio = results["adafruit_midi"] / results["tmidi_py"]
        print(f"tmidi (Python) is {ratio:.1f}x faster than adafruit_midi")
    print()
