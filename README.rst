Introduction
============


.. image:: https://readthedocs.org/projects/circuitpython-tmidi/badge/?version=latest
    :target: https://circuitpython-tmidi.readthedocs.io/
    :alt: Documentation Status
.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord
.. image:: https://github.com/todbot/CircuitPython_TMIDI/workflows/Build%20CI/badge.svg
    :target: https://github.com/todbot/CircuitPython_TMIDI/actions
    :alt: Build Status
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Code Style: Black

MIDI library for CircuitPython

TMIDI is a MIDI library for CircuitPython / MicroPython. It attempts to
be a provide a simpler API and perform faster, especially for MIDI parsing,
compared to ``adafruit_midi`` (`adafruit_midi github <https://github.com/adafruit/Adafruit_CircuitPython_MIDI/>`_)
TMIDI is derived from  ``winterbloom_smolmidi``
(`smolmidi github <https://github.com/wntrblm/Winterbloom_SmolMIDI>`_)
by Thea Flowers for Winterbloom.

Like ``adafruit_midi``, TMIDI works on CircuitPython's ``usb_midi`` and ``busio.UART``,
or any stream-like object that supports ``.readinto()`` and ``.write()``

For speed and latency compared to ``adafruit_midi``, see
`BENCHMARKS.md <https://github.com/todbot/CircuitPython_TMIDI/blob/HEAD/BENCHMARKS.md>`_.

Usage Example
=============

Sending MIDI over USB. Channels are 0-indexed, so ``channel=0`` is
MIDI channel 1:

.. code-block:: python

    import time
    import usb_midi
    import tmidi

    midi = tmidi.MIDI(midi_out=usb_midi.ports[1])

    while True:
        midi.send(tmidi.Message(tmidi.NOTE_ON, 60, 100, channel=0))
        time.sleep(0.5)
        midi.send(tmidi.Message(tmidi.NOTE_OFF, 60, 0, channel=0))
        time.sleep(0.5)

Receiving MIDI over USB. ``receive()`` returns ``None`` when nothing
has arrived:

.. code-block:: python

    import usb_midi
    import tmidi

    midi = tmidi.MIDI(midi_in=usb_midi.ports[0])

    while True:
        if msg := midi.receive():
            if msg.type == tmidi.NOTE_ON:
                print("note on:", msg.note, msg.velocity, msg.channel)
            else:
                print(msg)


Callbacks
=========

Instead of ``receive()``, register functions for the message types you want
and call ``poll()``. No ``Message`` objects are allocated.

.. code-block:: python

    def note_on(channel, note, velocity):
        print("note on:", channel, note, velocity)

    midi.on(tmidi.NOTE_ON, note_on)
    while True:
        midi.poll()

See ``examples/tmidi_simple_poll.py`` for a full example.

Turbo parser
============

TMIDI runs entirely in Python, but uses a faster ``@micropython.viper``
parser when your firmware can load native code. The parsers ship inside the
``tmidi/`` library folder as ``tmidi_kernel.<arch>.mpy``, and CircuitPython
picks the one for your board. ``tmidi.ENGINE`` says which parser is in use.

TMIDI 3.0 is a folder, ``lib/tmidi/``, instead of a single ``lib/tmidi.mpy``.
Delete an old ``lib/tmidi.mpy`` when upgrading.

======================  =====================================
``tmidi_kernel`` file   Boards
======================  =====================================
``armv6m``              RP2040
``armv7emsp``           SAMD51, nRF52840, RP2350, STM32F4
``xtensawin``           ESP32-S2, ESP32-S3
``rv32imc``             ESP32-C3, C5, C6
======================  =====================================

To rebuild them from ``src/tmidi_turbo.py``, use an ``mpy-cross`` from the
CircuitPython version they will run on. The files land in ``tmidi/``:

.. code-block:: shell

    cd src
    make MPY_CROSS=path/to/circuitpython/mpy-cross/build/mpy-cross



Dependencies
=============
This library depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.

Installing from PyPI
=====================

On supported GNU/Linux systems like the Raspberry Pi, you can install the driver locally `from
PyPI <https://pypi.org/project/circuitpython-tmidi/>`_.
To install for current user:

.. code-block:: shell

    pip3 install circuitpython-tmidi

To install system-wide (this may be required in some cases):

.. code-block:: shell

    sudo pip3 install circuitpython-tmidi

To install in a virtual environment in your current project:

.. code-block:: shell

    mkdir project-name && cd project-name
    python3 -m venv .venv
    source .env/bin/activate
    pip3 install circuitpython-tmidi

Installing to a Connected CircuitPython Device with Circup
==========================================================

Make sure that you have ``circup`` installed in your Python environment.
Install it with the following command if necessary:

.. code-block:: shell

    pip3 install circup

With ``circup`` installed and your CircuitPython device connected use the
following command to install:

.. code-block:: shell

    circup install tmidi

Or the following command to update an existing version:

.. code-block:: shell

    circup update


Documentation
=============
API documentation for this library can be found on `Read the Docs <https://circuitpython-tmidi.readthedocs.io/>`_.

For information on building library documentation, please check out
`this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Testing
=======

Install ``pytest`` with ``pip3 install pytest circuitpython-mocks --upgrade`` and run ``pytest -v``

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/todbot/CircuitPython_TMIDI/blob/HEAD/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
