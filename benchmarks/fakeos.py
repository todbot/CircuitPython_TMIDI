# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
#
# SPDX-License-Identifier: MIT

"""Stands in for os, so interface_trip_test.py can set getenv() values
without touching the board's settings.toml."""

SETTINGS = {}


def getenv(key, default=None):
    return SETTINGS.get(key, default)
