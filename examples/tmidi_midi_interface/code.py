# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
A fast USB <-> serial MIDI interface for any board with native USB and
busio.UART. Wire up a MIDI jack to the UART pins, or use a MIDI FeatherWing.

Copy code.py and boot.py from this directory to CIRCUITPY, plus one of
the settings files renamed to settings.toml: settings.toml documents every
setting, settings_<board>.toml are ready for those boards. Then edit it for
your board: UART pins, traffic LEDs, message types to drop each way, and
the USB names the computer shows.
If CIRCUITPY already has a settings.toml, add the TMIDI_ keys to it.

- The USB names are set in boot.py, so changing them needs a hard reset.
  Computers may remember the old names: on macOS, delete the device in
  Audio MIDI Setup.
- SysEx longer than TMIDI_SYSEX_SIZE is truncated.
- Serial MIDI is about 3 kB/s, so a big burst from USB holds up the loop
  while the UART sends it.
"""

import os

import board
import busio
import digitalio
import supervisor
import usb_midi
from micropython import const
from neopixel_write import neopixel_write

import tmidi

_TICKS_MASK = const(0x1FFFFFFF)  # supervisor.ticks_ms() wraps at 2**29

# data bytes for each type forwarded, SYSEX is handled on its own
MSG_DATA_LEN = {
    tmidi.NOTE_OFF: 2,
    tmidi.NOTE_ON: 2,
    tmidi.AFTERTOUCH: 2,
    tmidi.CC: 2,
    tmidi.PROGRAM_CHANGE: 1,
    tmidi.CHANNEL_PRESSURE: 1,
    tmidi.PITCH_BEND: 2,
    tmidi.SONG_POSITION: 2,
    tmidi.SONG_SELECT: 1,
    tmidi.BUS_SELECT: 1,
    tmidi.TUNE_REQUEST: 0,
    tmidi.CLOCK: 0,
    tmidi.TICK: 0,
    tmidi.START: 0,
    tmidi.CONTINUE: 0,
    tmidi.STOP: 0,
    tmidi.ACTIVE_SENSING: 0,
    tmidi.SYSTEM_RESET: 0,
}

SYSEX_START = b"\xf0"
SYSEX_END = b"\xf7"


def setting(key, default):
    val = os.getenv(key)
    if val is None:
        return default
    if isinstance(default, int):
        # newer CircuitPython getenv() returns strings even for ints
        return int(str(val), 0)
    return val


def board_pin(key, name):
    pin = getattr(board, name, None)
    if pin is None:
        raise ValueError("%s: no pin board.%s" % (key, name))
    return pin


def uart_pin(key, default):
    name = setting(key, default)
    return board_pin(key, name) if name else None


def mtypes(key):
    """Message types named in setting key, e.g. "CLOCK,ACTIVE_SENSING"."""
    types = []
    for name in setting(key, "").split(","):
        name = name.strip()
        if not name:
            continue
        mtype = getattr(tmidi, name, None)
        if mtype != tmidi.SYSEX and mtype not in MSG_DATA_LEN:
            raise ValueError("%s: unknown message type %s" % (key, name))
        types.append(mtype)
    return types


class Led:
    """A NeoPixel if named NEOPIXEL*, else one LED pin, or three for R,G,B."""

    def __init__(self, key, names, active_low):
        names = [name.strip() for name in names.split(",")]
        self._pixel = names[0].startswith("NEOPIXEL")
        self._active_low = active_low and not self._pixel
        self._pins = []
        for name in names:
            pin = digitalio.DigitalInOut(board_pin(key, name))
            pin.switch_to_output(self._active_low)
            self._pins.append(pin)
        if self._pixel:
            for power, value in (
                ("NEOPIXEL_POWER", True),
                ("NEOPIXEL_POWER_INVERTED", False),
            ):
                if hasattr(board, power):
                    self._power = digitalio.DigitalInOut(getattr(board, power))
                    self._power.switch_to_output(value)
        self._off = self.color(0)
        self._lit = None
        self.off()

    def color(self, rgb):
        """What on() takes to show 0xRRGGBB, made once since on() is hot."""
        if self._pixel:
            return bytes(((rgb >> 8) & 0xFF, (rgb >> 16) & 0xFF, rgb & 0xFF))
        if len(self._pins) == 1:
            return (bool(rgb) != self._active_low,)
        return tuple(bool(rgb & m) != self._active_low for m in (0xFF0000, 0xFF00, 0xFF))

    def on(self, color):
        if color is self._lit:
            return
        self._lit = color
        if self._pixel:
            neopixel_write(self._pins[0], color)
        else:
            for i in range(len(color)):
                self._pins[i].value = color[i]

    def off(self):
        self.on(self._off)


_leds = {}


def led(key):
    names = setting(key, "")
    if not names:
        return None
    if names not in _leds:
        _leds[names] = Led(key, names, setting("TMIDI_LED_ACTIVE_LOW", 0))
    return _leds[names]


class Link:
    """Forwards MIDI from midi_in to out_port, minus the types in drop."""

    def __init__(self, midi_in, out_port, drop, sysex_size, led, color):
        sx = None
        if sysex_size and tmidi.SYSEX not in drop:
            sx = bytearray(sysex_size)
        # hardware MIDI devices often send running status
        midi = self.midi = tmidi.MIDI(
            midi_in=midi_in,
            midi_out=out_port,
            enable_running_status=True,
            sysex_buffer=sx,
        )
        self.led = led
        self.color = led.color(color) if led else None
        self.lit_at = None
        hit = self.hit = bytearray(1)
        out = bytearray(3)

        def forwarder(mtype, n):
            def forward(channel, data0, data1):
                out[0] = mtype | channel
                out[1] = data0
                out[2] = data1
                # MIDI.write() adds ~30 µs/msg more on RP2040 @ 125 MHz.
                # so use out_port.write()
                # usb_midi takes a short message whole or not at all.
                out_port.write(out, n)
                hit[0] = 1

            return forward

        def forward_sysex(channel, n, data1):
            # write() keeps going when usb_midi takes only part of it
            if midi.write(SYSEX_START) and midi.write(sx, n):
                midi.write(SYSEX_END)
            hit[0] = 1

        for mtype, n in MSG_DATA_LEN.items():
            if mtype not in drop:
                self.midi.on(mtype, forwarder(mtype, n + 1))
        if sx is not None:
            self.midi.on(tmidi.SYSEX, forward_sysex)

    def poll(self, now):
        self.midi.poll()
        if self.hit[0]:
            self.hit[0] = 0
            if self.led:
                self.led.on(self.color)
                self.lit_at = now
        elif self.lit_at is not None and (now - self.lit_at) & _TICKS_MASK >= LED_MS:
            self.led.off()
            self.lit_at = None


LED_MS = setting("TMIDI_LED_MS", 20)
sysex_size = setting("TMIDI_SYSEX_SIZE", 256)

tx = uart_pin("TMIDI_UART_TX", "TX")
rx = uart_pin("TMIDI_UART_RX", "RX")
uart = busio.UART(
    tx=tx,
    rx=rx,
    baudrate=setting("TMIDI_UART_BAUD", 31250),
    timeout=0.001,
    receiver_buffer_size=setting("TMIDI_UART_RX_BUF", 512),
)

links = []
if tx:
    links.append(
        Link(
            usb_midi.ports[0],
            uart,
            mtypes("TMIDI_FILTER_TO_UART"),
            sysex_size,
            led("TMIDI_LED_TO_UART"),
            setting("TMIDI_COLOR_TO_UART", 0x000040),
        )
    )
if rx:
    links.append(
        Link(
            uart,
            usb_midi.ports[1],
            mtypes("TMIDI_FILTER_TO_USB"),
            sysex_size,
            led("TMIDI_LED_TO_USB"),
            setting("TMIDI_COLOR_TO_USB", 0x004000),
        )
    )

print("tmidi_midi_interface, %s parser, tx: %s rx: %s" % (tmidi.ENGINE, tx, rx))
print("drop to uart:", setting("TMIDI_FILTER_TO_UART", ""))
print("drop to usb: ", setting("TMIDI_FILTER_TO_USB", ""))

while True:
    now = supervisor.ticks_ms()
    for link in links:
        link.poll(now)
