# SPDX-FileCopyrightText: Copyright (c) 2019 Alethea Flowers for Winterbloom
# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
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

from micropython import const

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

_LEN_0_MESSAGES = set(
    [
        TUNE_REQUEST,
        SYSEX,
        SYSEX_END,
        CLOCK,
        TICK,
        START,
        CONTINUE,
        STOP,
        ACTIVE_SENSING,
        SYSTEM_RESET,
    ]
)
_LEN_1_MESSAGES = set([PROGRAM_CHANGE, CHANNEL_PRESSURE, SONG_SELECT, BUS_SELECT])
_LEN_2_MESSAGES = set([NOTE_OFF, NOTE_ON, AFTERTOUCH, CC, PITCH_BEND, SONG_POSITION])

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


def _read_byte(port):
    while not (buf := port.read(1)):
        pass
    return buf[0]


# def _read_n_bytes(port, buf, dest, num_bytes):
#     while num_bytes:
#         if port.readinto(buf):
#             dest.append(buf[0])
#             num_bytes -= 1


# def _read_byte_works(port):
#     while True:
#         buf = port.read(1)
#         if buf:
#             return buf[0]


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
        if mtype == PITCH_BEND and data1 == 0:
            self.pitch_bend = data0

    def __bytes__(self):
        status_byte = self.type
        if _is_channel_message(status_byte):
            status_byte |= self.channel
        if self.type in _LEN_2_MESSAGES:
            return bytes([status_byte, self.data0, self.data1])
        elif self.type in _LEN_1_MESSAGES:
            return bytes([status_byte, self.data0])
        return bytes([status_byte])

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        mtype = self.type
        type_str = "Message(" + _MSG_TYPE_NAMES.get(mtype, "Unknown")
        ch_str = "ch:%d" % self.channel if _is_channel_message(mtype) else "-"
        if mtype == PITCH_BEND:
            return "%s %s %d)" % (type_str, ch_str, self.pitch_bend)
        if mtype in _LEN_2_MESSAGES:
            return "%s %s %d %d)" % (type_str, ch_str, self.data0, self.data1)
        if mtype in _LEN_1_MESSAGES:
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

    def __init__(self, midi_in=None, midi_out=None, enable_running_status=False):
        self._in_port = midi_in
        self._out_port = midi_out
        self._running_status_enabled = enable_running_status
        self._running_status = None
        self._error_count = 0

        # This input buffer holds what has been read from midi_in
        self._read_buf = bytearray(1)

    @property
    def error_count(self):
        """Number of errors encountered when parsing received messages"""
        return self._error_count

    def receive(self):
        """Read message from MIDI port, parse that data and
        return the first MIDI message (event).
        This maintains the blocking characteristics of the midi_in port.
        Relies on the port to buffer the incoming unread MIDI messages.

        :returns Message object: Returns object or None for nothing.
        """

        # Read the status byte for the next message.
        # note: this will block if the port is set to have a timeout
        status_byte_buf = self._in_port.read(1)

        # No message ready.
        if not status_byte_buf:
            return None

        # Is this actually a status byte?
        status_byte = status_byte_buf[0]
        is_status = status_byte & 0x80

        # If not, see if we have a running status byte.
        if not is_status:
            if self._running_status_enabled and self._running_status:
                status_byte = self._running_status
            # If not a status byte and no running status, this is invalid data.
            else:
                self._error_count += 1
                return None

        message = Message(status_byte)

        # Is this a channel message, if so, let's figure out the right
        # message type and set the message's channel property.
        if _is_channel_message(status_byte):
            # Only set the running status byte for channel messages.
            self._running_status = status_byte
            # Mask off the channel nibble.
            message.type = status_byte & 0xF0
            message.channel = status_byte & 0x0F

        # Read the appropriate number of bytes for each message type.
        if message.type in _LEN_2_MESSAGES:
            message.data0 = _read_byte(self._in_port)
            message.data1 = _read_byte(self._in_port)
        elif message.type in _LEN_1_MESSAGES:
            message.data0 = _read_byte(self._in_port)

        # Check the data bytes for corruption. status bytes in data
        # means we're out of sync, so discard.
        # TODO: Figure out a better way to detect and deal with this upstream.
        for b in (message.data0 or 0, message.data1 or 0):
            if b & 0x80:
                self._error_count += 1
                return None

        return message

    def send(self, msg, channel=None):
        """Send a MIDI message.

        :param msg: Either a Message object or a sequence (list) of Message objects.
            The channel property will be *updated* as a side-effect of sending message(s).
        :param int channel: Channel number, if not set, the msg's channel will be used.
        """

        if isinstance(msg, Message):
            if channel:
                msg.channel = channel
            # bytes(object) does not work in uPy
            data = msg.__bytes__()
        else:
            data = bytearray()
            for each_msg in msg:
                if channel:
                    each_msg.channel = channel
                data.extend(each_msg.__bytes__())

        self._out_port.write(data, len(data))
