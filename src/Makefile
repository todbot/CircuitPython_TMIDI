# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
# Use an mpy-cross from the CircuitPython tree whose firmware will load the
# result, the .mpy version must match:
#   make MPY_CROSS=path/to/circuitpython/mpy-cross/build/mpy-cross
MPY_CROSS ?= mpy-cross
SRC ?= tmidi_turbo.py
OUT ?= build
ARCHES = armv6m armv7emsp xtensawin rv32imc

all: $(foreach a,$(ARCHES),$(OUT)/tmidi_kernel.$(a).mpy)

$(OUT)/tmidi_kernel.%.mpy: $(SRC)
	mkdir -p $(OUT)
	$(MPY_CROSS) -march=$* -o $@ $<

clean:
	rm -rf $(OUT)

.PHONY: all clean
