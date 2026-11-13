# tmidi benchmark results

tmidi compared with adafruit_midi on a Raspberry Pi Pico (RP2040):

- [USB-to-UART MIDI interface](#usb-to-uart-midi-interface): forwarding
  MIDI between a computer and a MIDI cable
- [Latency](#latency): time from a MIDI message arriving to code acting
  on it

## USB-to-UART MIDI interface

[examples/tmidi_midi_interface/](examples/tmidi_midi_interface/) forwards
MIDI between the board's USB port and a MIDI cable on its UART. Here it is
compared with the same interface written with adafruit_midi.

Tools, in [benchmarks/](benchmarks/):

- [interface_trip_test.py](benchmarks/interface_trip_test.py): runs on the
  computer. Starts the interface on the board over the REPL, sends MIDI
  through it both ways and checks what comes back. Its docstring lists
  the files to put on the board.
- [adafruit_midi_interface.py](benchmarks/adafruit_midi_interface.py): the
  interface done the usual adafruit_midi way, receive() then send()
- [fakeos.py](benchmarks/fakeos.py): feeds the interface its settings, so
  the board's own settings.toml isn't touched
- [forward_bench.py](benchmarks/forward_bench.py): runs on the board
  alone, for the CPU cost of forwarding each message

Setup:

- Raspberry Pi Pico (RP2040) @ 125 MHz, CircuitPython 11.0.0-alpha.3
- Pico UART on GP16 (TX) and GP17 (RX), wired to the DIN jacks of an
  H2MIDI-Pro USB-MIDI interface plugged into the same Mac
- tmidi interface: `settings_pico.toml` with no filters and the LEDs off
- tmidi Python: the same, with the viper parser turned off
- adafruit_midi 1.6.0, compiled to .mpy, default `in_buf_size` of 30

The tmidi viper run, from `benchmarks/`:

```sh
pip install python-rtmidi pyserial
python interface_trip_test.py --serial /dev/cu.usbmodem11101 \
    --board "Pico CircuitPython" --cable "H2MIDI-Pro Port 1" \
    --impl viper ../examples/tmidi_midi_interface/settings_pico.toml \
    TMIDI_UART_TX=GP16 TMIDI_UART_RX=GP17 TMIDI_FILTER_TO_USB= \
    TMIDI_LED_TO_UART= TMIDI_LED_TO_USB=
```

The other runs use `--impl python` and `--impl adafruit`.

### Round trip

| Test                           | tmidi viper | tmidi Python | adafruit_midi |
|--------------------------------|-------------|--------------|---------------|
| every message type             | 19 of 19    | 19 of 19     | 15 of 19      |
| 1000-note burst, USB to UART   | 0.96 s      | 0.97 s       | 3.05 s        |
| 1000-note burst, UART to USB   | 0.96 s      | 0.97 s       | 391 arrived   |
| both ways at once, USB to UART | all 1000    | all 1000     | all 1000      |
| both ways at once, UART to USB | all 1000    | all 1000     | 367 arrived   |
| round trip, USB to UART        | 2.67 (4.12) | 2.67 (3.71)  | 4.55 (7.22)   |
| round trip, UART to USB        | 2.66 (8.45) | 2.66 (6.76)  | 5.41 (8.80)   |
| no app reading the board's USB | ok          | ok           | ok            |

- Every message type: same result in both directions. adafruit_midi has
  no class for SONG_POSITION, SONG_SELECT or TUNE_REQUEST, so it can't
  forward them, and it loses a 299-byte SysEx, which doesn't fit its
  `in_buf_size`.
- Bursts: all 1000 arrived unless stated. 0.96 s is the fastest a
  31250 baud cable can carry them. How many adafruit_midi loses varies a
  little from run to run.
- Round trip: median (max) ms over 50 notes, including the H2MIDI and
  the Mac.
- No app reading: with nothing on the Mac reading the board's USB port,
  the interface keeps forwarding the other way, then recovers.
- The H2MIDI sends a status byte with every message, so running status
  isn't tested here.

### Forwarding cost

From forward_bench.py: 3000 NOTE_ON / CC / PITCH_BEND messages, best of 3,
read from memory and written to a pre-sized `io.BytesIO`.

| Forwarding with                     | µs/msg | bytes allocated/msg |
|-------------------------------------|--------|---------------------|
| tmidi viper, poll() + port.write    | 141.3  | 0                   |
| tmidi Python, poll() + port.write   | 252.1  | 0                   |
| tmidi viper, receive() + send()     | 432.4  | 48                  |
| tmidi Python, receive() + send()    | 542.4  | 48                  |
| adafruit_midi, receive() + send()   | 1563.6 | 299                 |

poll() + port.write is what `tmidi_midi_interface` does.

### Interface takeaways

- A 31250 baud cable carries about one message per ms. Both tmidi
  parsers forward a message in a fraction of that, so they keep up at
  wire speed with nothing lost. viper leaves ~110 µs/msg more CPU free.
- adafruit_midi takes ~1.6 ms per message, so it falls behind a busy
  cable and the Pico's 512-byte UART buffer overflows.
- adafruit_midi asks the UART for more bytes than have arrived, so each
  read waits for the 1 ms timeout. That adds ~2 ms to its round trips and
  slows its USB-to-UART burst to 3 s.
- receive() makes a Message for every message. poll() with callbacks
  doesn't, and is about 3x cheaper.

## Latency

Time from a MIDI message on the wire to CircuitPython code acting on it.

Tools:

- [examples/tmidi_latency_device.py](examples/tmidi_latency_device.py):
  runs on the board
- [examples/tmidi_latency_host.py](examples/tmidi_latency_host.py): runs
  on the computer, for the USB tests

Setup:

- Raspberry Pi Pico (RP2040) @ 125 MHz, CircuitPython 11.0.0-alpha.2
- tmidi with the pure Python parser
- Cells are median (p90) in ms
- "idle": the main loop only reads MIDI
- "busy": the main loop also does 5 ms of other work per pass
- Clock jitter: how far handled clocks land from their 20.8 ms spacing
  (120 BPM)

### UART

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

### USB

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

### Latency takeaways

- Single notes on an idle loop: all three are within about 2 ms.
- receive() (tmidi or adafruit_midi) handles one message per pass, so
  chords, clock and storms back up behind a busy loop. poll() handles
  everything waiting each pass and stays close to idle-loop numbers.
- For steady MIDI clock, use poll() and keep the main loop's passes short.
- The viper parser made idle-loop medians 0.1-0.7 ms faster and
  otherwise changed little.
