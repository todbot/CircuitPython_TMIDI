# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT
"""tmidi parser as a turbo (@micropython.viper) function.

Viper port of ``_parse_py`` in ``tmidi.py``. Keep the two in sync.

Build with ``src/Makefile``, firmware loads ``tmidi_kernel.<arch>.mpy``.
"""

import micropython
from micropython import const

# Keep in sync with the _ST_ slots in tmidi.py
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

_NEED_ONE = const(1)
_NEED_FIRST = const(2)
_NEED_SECOND = const(3)


@micropython.viper
def parse(buf: ptr8, st: ptr16, sx: ptr8) -> int:
    """Return next message from buf as status<<16|data0<<8|data1, 0 if drained."""
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
