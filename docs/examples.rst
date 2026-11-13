Simple test
------------

Show how to send MIDI messages.

.. literalinclude:: ../examples/tmidi_simpletest.py
    :caption: examples/tmidi_simpletest.py
    :linenos:


Simple receiver
---------------

Show to to receive MIDI messages.

.. literalinclude:: ../examples/tmidi_simple_receiver.py
    :caption: examples/tmidi_simple_receiver.py
    :linenos:


Simple poll
-----------

Show how to receive MIDI messages with callbacks and ``poll()``.

.. literalinclude:: ../examples/tmidi_simple_poll.py
    :caption: examples/tmidi_simple_poll.py
    :linenos:


Multiple receivers
------------------

Show to to receive MIDI messages from multiple receivers.

.. literalinclude:: ../examples/tmidi_multiple_receiver.py
    :caption: examples/tmidi_multiple_receiver.py
    :linenos:

Simple arpeggiator
------------------

Implement a simple arpeggiator that receives MIDI and sends it

.. literalinclude:: ../examples/tmidi_simple_arpeggiator.py
    :caption: examples/tmidi_simple_arpeggiator.py
    :linenos:

USB MIDI interface
------------------

A fast USB to serial MIDI interface for any board with ``busio.UART``.
Copy ``code.py`` and ``boot.py`` from ``examples/tmidi_midi_interface/``
to CIRCUITPY, plus one settings file renamed to ``settings.toml``.
``settings.toml`` documents every setting. ``settings_pico.toml``,
``settings_qtpy_rp2040.toml`` and ``settings_xiao_rp2040.toml`` are ready
for those boards. Edit the file to set the pins, LEDs, filters and
USB names.

.. literalinclude:: ../examples/tmidi_midi_interface/code.py
    :caption: examples/tmidi_midi_interface/code.py
    :linenos:

.. literalinclude:: ../examples/tmidi_midi_interface/boot.py
    :caption: examples/tmidi_midi_interface/boot.py
    :linenos:

.. literalinclude:: ../examples/tmidi_midi_interface/settings.toml
    :caption: examples/tmidi_midi_interface/settings.toml
    :language: toml
    :linenos:

.. literalinclude:: ../examples/tmidi_midi_interface/settings_pico.toml
    :caption: examples/tmidi_midi_interface/settings_pico.toml
    :language: toml
    :linenos:

.. literalinclude:: ../examples/tmidi_midi_interface/settings_qtpy_rp2040.toml
    :caption: examples/tmidi_midi_interface/settings_qtpy_rp2040.toml
    :language: toml
    :linenos:

.. literalinclude:: ../examples/tmidi_midi_interface/settings_xiao_rp2040.toml
    :caption: examples/tmidi_midi_interface/settings_xiao_rp2040.toml
    :language: toml
    :linenos:
