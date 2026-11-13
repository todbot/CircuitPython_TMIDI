# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

# Sets the USB identity of tmidi_midi_interface from settings.toml.
# USB names can only be changed in boot.py, so changes need a hard reset.

import os

import supervisor
import usb_midi


def settings(*pairs):
    """Map the settings.toml keys that are set to their keyword args."""
    kwargs = {}
    for key, arg in pairs:
        val = os.getenv(key)
        if val:
            kwargs[arg] = val
    return kwargs


ident = settings(
    ("TMIDI_USB_MANUFACTURER", "manufacturer"),
    ("TMIDI_USB_PRODUCT", "product"),
)
vid = os.getenv("TMIDI_USB_VID")
pid = os.getenv("TMIDI_USB_PID")
if vid and pid:
    # newer CircuitPython getenv() returns strings even for ints
    ident["vid"] = int(str(vid), 0)
    ident["pid"] = int(str(pid), 0)
if ident:
    supervisor.set_usb_identification(**ident)

names = settings(
    ("TMIDI_MIDI_INTERFACE_NAME", "streaming_interface_name"),
    ("TMIDI_MIDI_CONTROL_NAME", "audio_control_interface_name"),
    ("TMIDI_MIDI_IN_JACK_NAME", "in_jack_name"),
    ("TMIDI_MIDI_OUT_JACK_NAME", "out_jack_name"),
)
if names:
    usb_midi.set_names(**names)
