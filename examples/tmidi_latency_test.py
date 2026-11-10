# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
MIDI latency test: time from a message going out on the wire to the code
acting on it, for tmidi receive(), tmidi poll() and adafruit_midi receive().

"uart" mode (absolute numbers, needs nothing but a jumper):
  Jumper UART_TX to UART_RX (GP20 -> GP21 on a Pico). The board sends MIDI to
  itself and times each message from just before it is written to just after
  its handler runs. A 3-byte message takes 0.96 ms on the wire, so that is
  the floor. The board also does the sending, which costs it some time a
  real receiver would not spend, most of all in cc_storm.

"usb" mode (relative numbers):
  Run tmidi_latency_host.py on the computer. It sends each scenario on the
  same schedule this board computes, between start and end markers, and the
  board times each message against that schedule. There is no shared clock,
  so results are the delay over the best case seen in that scenario.

Scenarios:
  note         single note-ons with random gaps
  chord        8 note-ons at once
  clock_notes  MIDI clock at 120 BPM with note on/offs between the clocks;
               clock jitter is how far apart handled clocks land vs. 20.8 ms
  cc_storm     CCs back to back at MIDI wire speed for about 3 seconds

Each runs with an idle main loop and with WORK_MS of busy work per pass.
receive() handles one message per pass, poll() handles everything waiting.

Results are median / p90 / max in ms, and lost messages. Note the CPU
frequency printed first, as it changes every number here.

Copy tmidi and adafruit_midi (with the note_on, note_off, control_change and
timing_clock modules) to lib/ first.
"""

import array
import gc
import time

import board
import busio
import microcontroller
import usb_midi

import tmidi

MODE = "uart"  # "uart" | "usb"
UART_TX = board.GP20
UART_RX = board.GP21
LIBS = ("tmidi_receive", "tmidi_poll", "adafruit_midi")
SCENARIOS = ("note", "chord", "clock_notes", "cc_storm")  # keep in sync with host
WORK_MS = (0, 5)
TURBO = False  # True: tmidi uses the viper parser if it loaded
USB_LIB = "tmidi_poll"  # "usb" mode runs one library, restart to change it
USB_WORK_MS = 0

_ON = 0
_OFF = 1
_CC = 2
_CLK = 3
_KIND_NAMES = ("note_on", "note_off", "cc", "clock")
_STATUS = (0x90, 0x80, 0xB0, 0xF8)
_MARKER_CC = 127  # tmidi_latency_host.py: value = scenario number, 0 = end

_BYTE_US = 320  # one byte at 31250 baud
_TICK_US = 20_833  # MIDI clock at 120 BPM, 24 per quarter note
_RING = 4096  # note/cc send times, by sequence number
_MAX_SAMPLES = 4000

ns = time.monotonic_ns
_seed = [1]


def _rand(n):
    # tiny LCG so tmidi_latency_host.py can produce the same schedule
    _seed[0] = (_seed[0] * 75 + 74) % 65537
    return _seed[0] % n


def scenario_events(name):
    """Yield (due time in µs from start, kind), in time order"""
    _seed[0] = 1
    if name == "note":
        t = 0
        for _ in range(200):
            t += 3_000 + _rand(9_000)
            yield t, _ON
    elif name == "chord":
        for i in range(40):
            for _ in range(8):
                yield 20_000 + i * 60_000, _ON
    elif name == "cc_storm":
        for i in range(3000):
            yield i * 3 * _BYTE_US, _CC
    elif name == "clock_notes":
        on = True
        for i in range(192):
            t = i * _TICK_US
            yield t, _CLK
            for offset in sorted(1_000 + _rand(17_000) for _ in range(_rand(4))):
                yield t + offset, _ON if on else _OFF
                on = not on


def make_service(lib, port, handler):
    """Return a function that reads MIDI and calls handler(kind, data0, data1)"""
    if lib == "tmidi_poll":
        midi = tmidi.MIDI(midi_in=port, turbo=TURBO)
        midi.on(tmidi.NOTE_ON, lambda ch, d0, d1: handler(_ON, d0, d1))
        midi.on(tmidi.NOTE_OFF, lambda ch, d0, d1: handler(_OFF, d0, d1))
        midi.on(tmidi.CC, lambda ch, d0, d1: handler(_CC, d0, d1))
        midi.on(tmidi.CLOCK, lambda ch, d0, d1: handler(_CLK, 0, 0))
        return midi.poll

    if lib == "tmidi_receive":
        midi = tmidi.MIDI(midi_in=port, turbo=TURBO)

        def service():
            msg = midi.receive()
            if msg:
                if msg.type == tmidi.NOTE_ON:
                    handler(_ON, msg.data0, msg.data1)
                elif msg.type == tmidi.NOTE_OFF:
                    handler(_OFF, msg.data0, msg.data1)
                elif msg.type == tmidi.CC:
                    handler(_CC, msg.data0, msg.data1)
                elif msg.type == tmidi.CLOCK:
                    handler(_CLK, 0, 0)

        return service

    import adafruit_midi
    from adafruit_midi.control_change import ControlChange
    from adafruit_midi.note_off import NoteOff
    from adafruit_midi.note_on import NoteOn
    from adafruit_midi.timing_clock import TimingClock

    midi = adafruit_midi.MIDI(midi_in=port)

    def service():
        msg = midi.receive()
        if isinstance(msg, NoteOn):
            handler(_ON, msg.note, msg.velocity)
        elif isinstance(msg, NoteOff):
            handler(_OFF, msg.note, msg.velocity)
        elif isinstance(msg, ControlChange):
            handler(_CC, msg.control, msg.value)
        elif isinstance(msg, TimingClock):
            handler(_CLK, 0, 0)

    return service


def _next(events):
    # MicroPython's next() takes no default
    try:
        return next(events)
    except StopIteration:
        return None


def encode(kind, seq, buf):
    """Put a message for kind into buf with seq (0-8191) in its data bytes"""
    buf[0] = _STATUS[kind]
    if kind == _CLK:
        return 1
    if kind == _CC:
        buf[1] = (seq >> 7) & 0x3F
        buf[2] = seq & 0x7F
    else:
        buf[1] = seq & 0x7F
        buf[2] = 0x40 | ((seq >> 7) & 0x3F)  # never velocity 0
    return 3


def decode(kind, d0, d1):
    if kind == _CC:
        return d0 << 7 | d1
    return (d1 & 0x3F) << 7 | d0


def stats_ms(samples, base=0):
    s = sorted(samples)
    if not s:
        return "-"
    n = len(s)
    return "%.2f / %.2f / %.2f" % (
        (s[n // 2] - base) / 1000,
        (s[min(n - 1, n * 9 // 10)] - base) / 1000,
        (s[-1] - base) / 1000,
    )


class Recorder:
    """Keeps send times and records latency when a message is handled"""

    def __init__(self):
        self.t0 = ns()
        self.ring = array.array("l", [0] * _RING)
        self.clk_ring = array.array("l", [0] * 256)
        self.lat = [array.array("l") for _ in range(4)]
        self.sent = [0, 0, 0, 0]
        self.rx = [0, 0, 0, 0]
        self.intervals = array.array("l")
        self.last_clk = -1

    def now_us(self):
        return (ns() - self.t0) // 1000

    def sending(self, kind, seq, at_us):
        if kind == _CLK:
            self.clk_ring[self.sent[_CLK] & 255] = at_us
        else:
            self.ring[seq & (_RING - 1)] = at_us
        self.sent[kind] += 1

    def handled(self, kind, d0, d1):
        t = self.now_us()
        if kind == _CLK:
            sent_at = self.clk_ring[self.rx[_CLK] & 255]
            if self.last_clk >= 0 and len(self.intervals) < _MAX_SAMPLES:
                self.intervals.append(t - self.last_clk)
            self.last_clk = t
        else:
            sent_at = self.ring[decode(kind, d0, d1) & (_RING - 1)]
        self.rx[kind] += 1
        if len(self.lat[kind]) < _MAX_SAMPLES:
            self.lat[kind].append(t - sent_at)

    def report(self, label, relative=False):
        # relative: no shared clock, so report delay over the best case
        base = min(min(a) for a in self.lat if a) if relative and any(self.lat) else 0
        parts = []
        for kind in range(4):
            if self.sent[kind]:
                parts.append(
                    "%s %s (n=%d lost=%d)"
                    % (
                        _KIND_NAMES[kind],
                        stats_ms(self.lat[kind], base),
                        self.sent[kind],
                        self.sent[kind] - self.rx[kind],
                    )
                )
        if self.intervals:
            jitter = [abs(iv - _TICK_US) for iv in self.intervals]
            parts.append("clock jitter %s" % stats_ms(jitter))
        print(label, "|", " | ".join(parts))


def _label(lib, scenario, work_ms):
    name = lib + (" viper" if TURBO and lib.startswith("tmidi") else "")
    return "%-20s %-11s work=%dms" % (name, scenario, work_ms)


def _busy(us, pump=None):
    end = ns() + us * 1000
    while ns() < end:
        if pump:
            pump()


def run_uart(lib, scenario, work_ms):
    uart = busio.UART(tx=UART_TX, rx=UART_RX, baudrate=31250, timeout=0.001)
    rec = Recorder()
    service = make_service(lib, uart, rec.handled)
    events = scenario_events(scenario)
    upcoming = _next(events)
    buf = bytearray(3)
    seq = 0
    wire_free = 0  # µs when the last byte written will have left
    gc.collect()
    rec.t0 = ns()

    def pump():
        nonlocal upcoming, seq, wire_free
        t = rec.now_us()
        # keep the TX FIFO nearly empty so write() never blocks
        while upcoming and t >= upcoming[0] and wire_free - t < 1000:
            kind = upcoming[1]
            n = encode(kind, seq, buf)
            start = max(t, wire_free)
            rec.sending(kind, seq, start)
            uart.write(buf[:n])
            wire_free = start + n * _BYTE_US
            seq = (seq + 1) & 0x1FFF
            upcoming = _next(events)
            t = rec.now_us()

    while True:
        service()
        pump()
        if upcoming is None and (
            sum(rec.rx) == sum(rec.sent) or rec.now_us() - wire_free > 500_000
        ):
            break
        if work_ms:
            _busy(work_ms * 1000, pump)
    uart.deinit()
    rec.report(_label(lib, scenario, work_ms))


def usb_record(lib, work_ms):
    """Time scenarios sent by tmidi_latency_host.py over USB, forever"""
    state = {"rec": None, "scenario": ""}

    def handler(kind, d0, d1):
        rec = state["rec"]
        if kind == _CC and d0 == _MARKER_CC:
            if d1:
                state["scenario"] = SCENARIOS[d1 - 1]
                rec = Recorder()
                seq = 0
                for due, k in scenario_events(state["scenario"]):
                    rec.sending(k, seq, due)
                    seq = (seq + 1) & 0x1FFF
                rec.t0 = ns()
                state["rec"] = rec
            elif rec:
                rec.report(_label(lib, state["scenario"], work_ms), relative=True)
                state["rec"] = None
                gc.collect()
        elif rec:
            rec.handled(kind, d0, d1)

    service = make_service(lib, usb_midi.ports[0], handler)
    print("USB ready:", lib, "work=%dms" % work_ms, "engine", tmidi.ENGINE)
    while True:
        service()
        if work_ms:
            _busy(work_ms * 1000)


print(
    "cpu_hz", microcontroller.cpu.frequency, "tmidi engine", tmidi.ENGINE, "turbo", TURBO
)
if __name__ == "__main__":
    if MODE == "usb":
        usb_record(USB_LIB, USB_WORK_MS)
    else:
        for scenario in SCENARIOS:
            for work_ms in WORK_MS:
                for lib in LIBS:
                    run_uart(lib, scenario, work_ms)
                    gc.collect()
