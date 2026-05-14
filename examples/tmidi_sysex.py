# SPDX-FileCopyrightText: Copyright (c) 2024 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""
# in CPython this looks like:

import rtmidi, time
midiin = rtmidi.MidiIn(); midiout = rtmidi.MidiOut()
midiin.open_port(0);      midiout.open_port(0)
midiin.ignore_types(sysex=False)
midiout.send_message(bytes([0xf0, 0x7e, 0x7f, 0x06, 0x01, 0xf7]))  # device inquiry 0x7f means 'any device'
time.sleep(0.01)
resp = midiin.get_message()
print(resp)

"""
