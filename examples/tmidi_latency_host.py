#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

# USB MIDI latency test host, for tmidi_latency_device.py in "usb" mode.
#
# Sends each scenario on the schedule the board also computes, between
# start and end markers. The board times what it handles against that
# schedule and prints the results on its serial console.
#
# Usage:
#   python tmidi_latency_host.py [--port "CircuitPython"] [scenario ...]
#
# Dependencies: pip install mido python-rtmidi

import argparse
import sys
import time

import mido

ON, OFF, CC, CLK = range(4)
SCENARIOS = ("note", "chord", "clock_notes", "cc_storm")  # keep in sync with board
MARKER_CC = 127
BYTE_US = 320
TICK_US = 20_833
LEAD = 0.5  # seconds between start marker and first message, for the board to set up

_seed = [1]


def _rand(n):
    # same LCG as tmidi_latency_device.py
    _seed[0] = (_seed[0] * 75 + 74) % 65537
    return _seed[0] % n


def scenario_events(name):
    """Yield (due time in µs from start, kind), as tmidi_latency_device.py does"""
    _seed[0] = 1
    if name == "note":
        t = 0
        for _ in range(200):
            t += 3_000 + _rand(9_000)
            yield t, ON
    elif name == "chord":
        for i in range(40):
            for _ in range(8):
                yield 20_000 + i * 60_000, ON
    elif name == "cc_storm":
        for i in range(3000):
            yield i * 3 * BYTE_US, CC
    elif name == "clock_notes":
        on = True
        for i in range(192):
            t = i * TICK_US
            yield t, CLK
            for offset in sorted(1_000 + _rand(17_000) for _ in range(_rand(4))):
                yield t + offset, ON if on else OFF
                on = not on


def encode(kind, seq):
    if kind == CLK:
        return [0xF8]
    if kind == CC:
        return [0xB0, (seq >> 7) & 0x3F, seq & 0x7F]
    return [(0x90, 0x80)[kind], seq & 0x7F, 0x40 | ((seq >> 7) & 0x3F)]


def run(out, scenario):
    out.send(
        mido.Message(
            "control_change", control=MARKER_CC, value=SCENARIOS.index(scenario) + 1
        )
    )
    time.sleep(LEAD)
    seq = 0
    t0 = time.perf_counter()
    for due, kind in scenario_events(scenario):
        while (time.perf_counter() - t0) * 1e6 < due:
            pass
        out.send(mido.Message.from_bytes(encode(kind, seq)))
        seq = (seq + 1) & 0x1FFF
    time.sleep(1)
    out.send(mido.Message("control_change", control=MARKER_CC, value=0))
    print("sent", scenario)
    time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="tmidi USB MIDI latency test host")
    parser.add_argument(
        "--port", default="CircuitPython", help="part of the board's port name"
    )
    parser.add_argument("scenarios", nargs="*", default=list(SCENARIOS))
    args = parser.parse_args()

    out_name = next((n for n in mido.get_output_names() if args.port in n), None)
    if not out_name:
        sys.exit("No MIDI port matching %r: %s" % (args.port, mido.get_output_names()))
    print("Port:", out_name, "- results print on the board's serial console")
    with mido.open_output(out_name) as out:
        for scenario in args.scenarios:
            run(out, scenario)


if __name__ == "__main__":
    main()
