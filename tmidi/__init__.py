# SPDX-FileCopyrightText: Copyright (c) 2019 Alethea Flowers for Winterbloom
# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT
"""
`tmidi`
================================================================================

MIDI library for CircuitPython


* Author(s): Tod Kurt, with code from Alethea Flowers for Winterbloom

* Portions of this library come from Winterbloom_SmolMIDI:
  https://github.com/wntrblm/Winterbloom_SmolMIDI

Implementation Notes
--------------------

**Hardware:**

* Native USB for USB MIDI
* UART for Serial MIDI
* PIO-USB or MAX3421E USB Host for USB Host MIDI

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

"""

# imports

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/todbot/CircuitPython_TMIDI.git"

# Portions of this library come from Winterbloom_SmolMIDI:
#
# The MIT License (MIT)
#
# Copyright (c) 2019 Alethea Flowers for Winterbloom
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from array import array

from micropython import const

# Prebuilt per chip as tmidi_kernel.<arch>.mpy from src/tmidi_turbo.py.
# Missing on Blinka and on firmware without native code.
try:
    from tmidi.tmidi_kernel import parse as _kernel_parse
except (ImportError, ValueError):
    _kernel_parse = None

ENGINE = "Python" if _kernel_parse is None else "viper"
"""``"viper"`` when the turbo parser loaded, else ``"Python"``."""

# Message type constants.
NOTE_OFF = const(0x80)
"""Note Off"""
NOTE_ON = const(0x90)
"""Note On"""
AFTERTOUCH = const(0xA0)
"""Aftertouch"""
CONTROLLER_CHANGE = CC = const(0xB0)
"""Controller Change"""
PROGRAM_CHANGE = const(0xC0)
"""Program Change"""
CHANNEL_PRESSURE = const(0xD0)
"""Channel Pressure"""
PITCH_BEND = const(0xE0)
"""Pitch Bend"""
SYSTEM_EXCLUSIVE = SYSEX = const(0xF0)
"""Sysex"""
SONG_POSITION = const(0xF2)
"""Song Position"""
SONG_SELECT = const(0xF3)
"""Song Select"""
BUS_SELECT = const(0xF5)
"""BUS Select"""
TUNE_REQUEST = const(0xF6)
"""Tune Request"""
SYSEX_END = const(0xF7)
"""Sysex End"""
CLOCK = const(0xF8)
"""Clock"""
TICK = const(0xF9)
"""Tick"""
START = const(0xFA)
"""Start"""
CONTINUE = const(0xFB)
"""Continue"""
STOP = const(0xFC)
"""Stop"""
ACTIVE_SENSING = const(0xFE)
"""Active Sensing"""
SYSTEM_RESET = const(0xFF)
"""System Reset"""

_MSG_DATA_LEN = {
    NOTE_OFF: 2,
    NOTE_ON: 2,
    AFTERTOUCH: 2,
    CC: 2,
    PITCH_BEND: 2,
    SONG_POSITION: 2,
    PROGRAM_CHANGE: 1,
    CHANNEL_PRESSURE: 1,
    SONG_SELECT: 1,
    BUS_SELECT: 1,
}

# Pre-allocated scratch buffer for __bytes__() — avoids per-call list allocation.
# Safe because CircuitPython is single-threaded.
_msg_buf = bytearray(3)

_MSG_TYPE_NAMES = {
    NOTE_OFF: "NoteOff",
    NOTE_ON: "NoteOn",
    AFTERTOUCH: "Aftertouch",
    CC: "CC",
    PROGRAM_CHANGE: "ProgramChange",
    CHANNEL_PRESSURE: "ChannelPressure",
    PITCH_BEND: "PitchBend",
    SYSEX: "Sysex",
    SONG_POSITION: "SongPosition",
    SONG_SELECT: "SongSelect",
    BUS_SELECT: "BusSelect",
    TUNE_REQUEST: "TuneRequest",
    SYSEX_END: "SysexEnd",
    CLOCK: "Clock",
    TICK: "Tick",
    START: "Start",
    CONTINUE: "Continue",
    STOP: "Stop",
    ACTIVE_SENSING: "ActiveSensing",
    SYSTEM_RESET: "SystemReset",
}


def _is_channel_message(status_byte):
    return status_byte >= NOTE_OFF and status_byte < SYSEX


# Keep in sync with the _ST_ slots in src/tmidi_turbo.py
_ST_RD = const(0)
_ST_WR = const(1)
_ST_STATUS = const(2)
_ST_NEED = const(3)
_ST_DATA0 = const(4)
_ST_SX_LEN = const(5)
_ST_SX_CAP = const(6)
_ST_ERRORS = const(7)
_ST_RUNNING = const(8)
_ST_RUNNING_ON = const(9)
_ST_SIZE = const(10)

_NEED_ONE = const(1)
_NEED_FIRST = const(2)
_NEED_SECOND = const(3)

_READ_SIZE = const(64)
_MAX_SYSEX = const(65535)

_NO_SYSEX = bytearray(0)


def _parse_py(buf, st, sx):
    """Return next message from buf as status<<16|data0<<8|data1, 0 if drained.

    Keep in sync with the viper version in src/tmidi_turbo.py.
    """
    rd = st[_ST_RD]
    wr = st[_ST_WR]
    status = st[_ST_STATUS]
    need = st[_ST_NEED]

    while rd < wr:
        b = buf[rd]
        rd += 1

        # real-time can land inside any message and must not disturb it
        if b >= 0xF8:
            st[_ST_RD] = rd
            st[_ST_STATUS] = status
            st[_ST_NEED] = need
            return b << 16

        if b >= 0x80:
            if b == 0xF7 and status == 0xF0:
                st[_ST_RD] = rd
                st[_ST_STATUS] = 0
                st[_ST_NEED] = 0
                return 0xF00000 | st[_ST_SX_LEN]

            if status != 0:
                st[_ST_ERRORS] = (st[_ST_ERRORS] + 1) & 0xFFFF

            status = b
            if b < 0xF0:
                if st[_ST_RUNNING_ON] != 0:
                    st[_ST_RUNNING] = b
                if (b & 0xE0) == 0xC0:
                    need = _NEED_ONE
                else:
                    need = _NEED_FIRST
                continue

            st[_ST_RUNNING] = 0
            if b == 0xF0:
                need = 0
                st[_ST_SX_LEN] = 0
                continue
            if b == 0xF2:
                need = _NEED_FIRST
                continue
            if b == 0xF3 or b == 0xF5:
                need = _NEED_ONE
                continue

            st[_ST_RD] = rd
            st[_ST_STATUS] = 0
            st[_ST_NEED] = 0
            return b << 16

        if status == 0xF0:
            n = st[_ST_SX_LEN]
            if n < st[_ST_SX_CAP]:
                sx[n] = b
                st[_ST_SX_LEN] = n + 1
            continue

        if status == 0:
            status = st[_ST_RUNNING]
            if status == 0:
                st[_ST_ERRORS] = (st[_ST_ERRORS] + 1) & 0xFFFF
                continue
            if (status & 0xE0) == 0xC0:
                need = _NEED_ONE
            else:
                need = _NEED_FIRST

        if need == _NEED_FIRST:
            st[_ST_DATA0] = b
            need = _NEED_SECOND
            continue

        st[_ST_RD] = rd
        st[_ST_STATUS] = 0
        st[_ST_NEED] = 0
        if need == _NEED_SECOND:
            return status << 16 | st[_ST_DATA0] << 8 | b
        return status << 16 | b << 8

    st[_ST_RD] = rd
    st[_ST_STATUS] = status
    st[_ST_NEED] = need
    return 0


class Message:
    """
    MIDI Message.

    :param mtype: The type of message, e.g. tmidi.NOTE_ON.
    :param data0: The first data byte for this message,
        e.g. the note number as an ``int`` (0-127) for NOTE_ON messages.
    :param data1: The second data byte for this message,
        e.g. the velocity (0-127) for NOTE_ON messages.
    :param channel: The MIDI channel for this message, if applicable (0-15)

    Example of creating Messages:

    .. code-block:: python

        # create Note On middle-C message on ch 1 (0-indexed)
        m = Message(tmidi.NOTE_ON, 60, 127, channel=0)
        # create CC 74 with val 63 on ch 4
        m = Message(tmidi.CC, 74, 63, channel=4-1)
        # create a pitch bend full up on ch 1
        m = Message(tmidi.PITCH_BEND, 8191)

    Example of creating accessing Message attributes:

    .. code-block:: python

        if msg := midi.receive():
            if msg.type == tmidi.NOTE_ON:
              print("note on:", msg.note, msg.velocity)
            elif msg.type == tmidi.NOTE_OFF:
              print("note off:", msg.note, msg.velocity)
            elif msg.type == tmidi.PROGRAM_CHANGE:
              print("program change:", msg.value)
    """

    def __init__(self, mtype=SYSTEM_RESET, data0=0, data1=0, channel=0):
        self.type = mtype
        self.channel = channel
        self.data0 = data0
        self.data1 = data1
        if mtype == PITCH_BEND and data1 == 0 and not (0 <= data0 <= 0x7F):
            self.pitch_bend = data0

    def __bytes__(self):
        status_byte = self.type
        if _is_channel_message(status_byte):
            status_byte |= self.channel
        _msg_buf[0] = status_byte
        n = _MSG_DATA_LEN.get(self.type, 0)
        if n == 2:
            _msg_buf[1] = self.data0
            _msg_buf[2] = self.data1
            return bytes(_msg_buf)
        if n == 1:
            _msg_buf[1] = self.data0
            return bytes(_msg_buf[:2])
        return bytes(_msg_buf[:1])

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        mtype = self.type
        type_str = "Message(" + _MSG_TYPE_NAMES.get(mtype, "Unknown")
        ch_str = "ch:%d" % self.channel if _is_channel_message(mtype) else "-"
        if mtype == PITCH_BEND:
            return "%s %s %d)" % (type_str, ch_str, self.pitch_bend)
        if mtype == SYSEX:
            if self.data0:
                return "%s %d bytes)" % (type_str, self.data0)
            return "%s)" % type_str
        n = _MSG_DATA_LEN.get(mtype, 0)
        if n == 2:
            return "%s %s %d %d)" % (type_str, ch_str, self.data0, self.data1)
        if n == 1:
            return "%s %s %d)" % (type_str, ch_str, self.data0)
        return "%s)" % type_str

    @property
    def note(self):
        """MIDI note number of message (only valid for NOTE_ON/NOTE_OFF msgs)"""
        return self.data0

    @note.setter
    def note(self, notenum):
        self.data0 = notenum

    @property
    def velocity(self):
        """MIDI velocity of message (only valid for NOTE_ON/NOTE_OFF msgs)"""
        return self.data1

    @velocity.setter
    def velocity(self, vel):
        self.data1 = vel

    @property
    def pitch_bend(self):
        """Pitch bend value of message (only valid for PITCH_BEND msgs)"""
        return (self.data1 << 7 | self.data0) - 8192

    @pitch_bend.setter
    def pitch_bend(self, pbval):
        pbval += 8192
        self.data0 = pbval & 0x7F
        self.data1 = pbval >> 7

    @property
    def value(self):
        """Message value, only valid for len1 messages (Program Change, etc)"""
        return self.data0

    @value.setter
    def value(self, val):
        self.data0 = val


class MIDI:
    """
    MIDI Parser, receiver and sender
    ``midi_in`` or ``midi_out`` *must* be set or both together.

    :param midi_in: an object which implements ``read(length)``,
        set to ``usb_midi.ports[0]`` for USB MIDI, default None.
    :param midi_out: an object which implements ``write(buffer, length)``,
        set to ``usb_midi.ports[1]`` for USB MIDI, default None.
    :param bool enable_running_status: Allow running status messages to work, default False.
    :param bytearray sysex_buffer: Optional pre-allocated buffer for capturing SysEx payloads.
        When provided, received SysEx payload bytes are written into this buffer and
        ``msg.data0`` on the returned message holds the number of bytes written.
        If the payload exceeds the buffer length, the overflow is consumed and discarded
        so the stream stays in sync. When ``None`` (default), SysEx payloads are discarded
        and ``msg.data0`` is 0.
    :param bool turbo: Use the viper parser if it loaded (see ``ENGINE``), default True.

    Example of receiving with callbacks, which avoids allocating ``Message`` objects:

    .. code-block:: python

        import usb_midi
        import tmidi

        def note_on(channel, note, velocity):
            print("note on:", channel, note, velocity)

        midi = tmidi.MIDI(midi_in=usb_midi.ports[0])
        midi.on(tmidi.NOTE_ON, note_on)

        while True:
            midi.poll()

    Example of receiving SysEx with payload capture:

    .. code-block:: python

        import usb_midi
        import tmidi
        sysex_buf = bytearray(128)
        midi = tmidi.MIDI(midi_in=usb_midi.ports[0], sysex_buffer=sysex_buf)

        while True:
            if msg := midi.receive():
                if msg.type == tmidi.SYSEX:
                    payload = memoryview(sysex_buf)[: msg.data0]
                    print("SysEx:", list(payload))

    Example of sending MIDI over USB:

    .. code-block:: python

        import usb_midi
        import tmidi
        midi_usb = tmidi.MIDI(midi_out=usb_midi.ports[1])
        msg_on = tmidi.Message(tmidi.NOTE_ON, notenum, velocity)
        midi_usb.send(msg_on)

    Example of sending MIDI over UART (TRS or 5-pin):

    .. code-block:: python

        import board
        import busio
        import tmidi
        uart = busio.UART(tx=board.TX, rx=board.RX, timeout=0.001)
        midi_uart = tmidi.MIDI(midi_out=uart)
        msg_on = tmidi.Message(tmidi.NOTE_ON, notenum, velocity)
        midi_uart.send(msg_on)

    Example of receiving MIDI:

    .. code-block:: python

        import board
        import busio
        import usb_midi
        import tmidi
        uart = busio.UART(tx=board.TX, rx=board.RX, timeout=0.001)
        midi_uart = tmidi.MIDI(midi_in=uart, midi_out=uart)
        midi_usb = tmidi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1])

        while True:
            if msg := midi_usb.receive():
                print("usb midi:", msg)
            if msg := midi_uart.receive():
                print("uart midi:", msg)
    """

    def __init__(
        self,
        midi_in=None,
        midi_out=None,
        enable_running_status=False,
        sysex_buffer=None,
        turbo=True,
    ):
        self._in_port = midi_in
        self._out_port = midi_out
        self._has_in_waiting = hasattr(midi_in, "in_waiting")
        self._parse = _kernel_parse if turbo and _kernel_parse else _parse_py
        self._callbacks = {}

        self._bulk_read = True
        self._one = bytearray(1)
        self._buf = bytearray(_READ_SIZE)
        self._sx = _NO_SYSEX if sysex_buffer is None else sysex_buffer
        self._st = array("H", [0] * _ST_SIZE)
        self._st[_ST_SX_CAP] = min(len(self._sx), _MAX_SYSEX)
        self._st[_ST_RUNNING_ON] = 1 if enable_running_status else 0

    @property
    def error_count(self):
        """Number of errors encountered when parsing received messages"""
        return self._st[_ST_ERRORS]

    def _fill(self):
        n = _READ_SIZE
        if self._has_in_waiting:
            # a large readinto on UART would block toward its timeout
            n = min(self._in_port.in_waiting, _READ_SIZE)
            if not n:
                return 0
        if self._bulk_read:
            try:
                n = self._in_port.readinto(self._buf, n) or 0
            except TypeError:
                # adafruit_usb_host_midi has readinto(buf), which must be filled exactly
                self._bulk_read = False
                return self._fill()
        else:
            n = self._in_port.readinto(self._one) or 0
            if n:
                self._buf[0] = self._one[0]
        self._st[_ST_RD] = 0
        self._st[_ST_WR] = n
        return n

    def receive(self):
        """Read from MIDI port, parse that data and return the next MIDI message.
        Does not wait: a partly received message is kept until the rest arrives.

        :returns Message object: Returns object or None for nothing.
        """
        parse = self._parse
        buf = self._buf
        st = self._st
        sx = self._sx

        r = parse(buf, st, sx)
        while not r:
            if not self._fill():
                return None
            r = parse(buf, st, sx)

        status = r >> 16
        if status < SYSEX:
            return Message(status & 0xF0, (r >> 8) & 0xFF, r & 0xFF, status & 0x0F)
        if status == SYSEX:
            return Message(SYSEX, r & 0xFFFF)
        return Message(status, (r >> 8) & 0xFF, r & 0xFF)

    def on(self, mtype, func):
        """Register a function to be called by :meth:`poll` for a type of message.
        There is one function per message type.

        :param int mtype: The type of message, e.g. ``tmidi.NOTE_ON``.
        :param func: Called as ``func(channel, data0, data1)`` with the raw data bytes.
            ``channel`` is 0 for system messages. For ``tmidi.SYSEX``, ``data0`` is
            the number of bytes written to ``sysex_buffer``.
            Use ``None`` to unregister.
        """
        if func is None:
            self._callbacks.pop(mtype, None)
        else:
            self._callbacks[mtype] = func

    def poll(self, limit=32):
        """Parse waiting MIDI data, calling functions registered with :meth:`on`.

        :param int limit: Most messages to handle, so a busy port can't starve
            the main loop.
        :returns int: Number of messages parsed
        """
        parse = self._parse
        buf = self._buf
        st = self._st
        sx = self._sx
        callbacks = self._callbacks

        count = 0
        while count < limit:
            r = parse(buf, st, sx)
            while not r:
                if not self._fill():
                    return count
                r = parse(buf, st, sx)
            count += 1

            status = r >> 16
            if status < SYSEX:
                func = callbacks.get(status & 0xF0)
                if func:
                    func(status & 0x0F, (r >> 8) & 0xFF, r & 0xFF)
            elif status == SYSEX:
                func = callbacks.get(SYSEX)
                if func:
                    func(0, r & 0xFFFF, 0)
            else:
                func = callbacks.get(status)
                if func:
                    func(0, (r >> 8) & 0xFF, r & 0xFF)
        return count

    def send(self, msg, channel=None):
        """Send a MIDI message.

        :param msg: Either a Message object or a sequence (list) of Message objects.
            The channel property will be *updated* as a side-effect of sending message(s).
        :param int channel: Channel number, if not set, the msg's channel will be used.
        """

        if isinstance(msg, Message):
            if channel is not None:
                msg.channel = channel
            # bytes(object) does not work in uPy
            data = msg.__bytes__()
        else:
            data = bytearray()
            for each_msg in msg:
                if channel is not None:
                    each_msg.channel = channel
                data.extend(each_msg.__bytes__())

        self._out_port.write(data, len(data))
