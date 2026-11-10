# tmidi latency results

Time from a MIDI message on the wire to CircuitPython code acting on it,
from `examples/tmidi_latency_device.py` (and `tmidi_latency_host.py` for
USB).

- Raspberry Pi Pico (RP2040) @ 125 MHz, CircuitPython 11.0.0-alpha.2
- tmidi with the pure Python parser
- Cells are median (p90) in ms
- "idle": the main loop only reads MIDI
- "busy": the main loop also does 5 ms of other work per pass
- Clock jitter: how far handled clocks land from their 20.8 ms spacing
  (120 BPM)

## UART

Absolute, via a GP20 -> GP21 loopback. A 3-byte message takes 0.96 ms on
the wire, which is included. The Pico also does the sending here, so CC
storm losses are pessimistic.

Idle loop:

| Scenario        | tmidi receive()  | tmidi poll() | adafruit_midi    |
|-----------------|------------------|--------------|------------------|
| note            | 2.05 (2.17)      | 1.89 (1.95)  | 3.84 (4.49)      |
| chord, 8 notes  | 4.95 (5.39)      | 1.85 (2.20)  | 16.19 (18.17)    |
| clock           | 1.68 (1.80)      | 1.43 (1.56)  | 3.57 (4.21)      |
| clock jitter    | 0.14 (0.48)      | 0.13 (0.39)  | 0.62 (2.60)      |
| CC storm        | 68.5, 1403 lost  | 1.88 (2.14)  | 139, 1982 lost   |

Busy loop:

| Scenario        | tmidi receive()  | tmidi poll() | adafruit_midi    |
|-----------------|------------------|--------------|------------------|
| note            | 5.52 (10.71)     | 4.03 (6.44)  | 71.72 (80.99)    |
| chord, 8 notes  | 23.72 (40.16)    | 5.07 (7.20)  | 70.67 (94.29)    |
| clock           | 6.80 (14.65)     | 3.97 (6.62)  | 57.71 (91.13)    |
| clock jitter    | 3.55 (8.90)      | 2.40 (5.01)  | 8.59 (14.15)     |
| CC storm        | 288, 2563 lost   | 5.79 (7.37)  | 285, 2702 lost   |

CC storm: 3000 CCs back to back at wire speed.

## USB

Relative: the Mac and the Pico share no clock, so these are the delay over
the fastest message seen in each run. No USB run lost messages; "behind"
means it had not caught up with the storm when the run ended.

Idle loop:

| Scenario        | tmidi receive()  | tmidi poll() | adafruit_midi    |
|-----------------|------------------|--------------|------------------|
| note            | 0.15 (0.22)      | 0.14 (0.21)  | 0.46 (0.77)      |
| chord, 8 notes  | 2.94 (5.13)      | 2.31 (4.20)  | 6.99 (12.31)     |
| clock           | 0.11 (0.17)      | 0.11 (0.18)  | 0.34 (0.55)      |
| clock jitter    | 0.05 (0.13)      | 0.04 (0.13)  | 0.14 (0.42)      |
| CC storm        | 8.20 (14.25)     | 0.92 (1.07)  | behind           |

Busy loop:

| Scenario        | tmidi receive()  | tmidi poll() | adafruit_midi    |
|-----------------|------------------|--------------|------------------|
| note            | 4.32 (7.31)      | 2.80 (5.12)  | 17.03 (33.75)    |
| chord, 8 notes  | 23.65 (43.10)    | 4.21 (6.99)  | 27.35 (50.38)    |
| clock           | 4.59 (10.62)     | 2.55 (4.61)  | 7.52 (21.69)     |
| clock jitter    | 3.37 (5.17)      | 2.27 (3.74)  | 5.27 (12.32)     |
| CC storm        | behind           | 2.97 (6.37)  | behind           |

## Takeaways

- Single notes on an idle loop: all three are within about 2 ms.
- receive() (tmidi or adafruit_midi) handles one message per pass, so
  chords, clock and storms back up behind a busy loop. poll() handles
  everything waiting each pass and stays close to idle-loop numbers.
- For steady MIDI clock, use poll() and keep the main loop's passes short.
- The viper parser made idle-loop medians 0.1-0.7 ms faster and
  otherwise changed little.
