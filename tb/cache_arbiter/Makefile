# Makefile

# 1. Define the Simulator
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# 2. Define the Paths to your Source Code
VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_interface.sv
VERILOG_SOURCES += $(PWD)/../../src/cache_arbiter.sv
VERILOG_SOURCES += $(PWD)/arbiter_axi_wrapper.sv

# 3. Define the Top-Level Module
# The flat-signal wrapper, so cocotbext-axi can attach the AxiRam + AxiMasters.
TOPLEVEL = arbiter_axi_wrapper

# 4. Define the Python Test Module
MODULE = test_cache_arbiter

# 5. Enable Waveforms (Trace)
EXTRA_ARGS += --trace --trace-structs

# 6. Include the Standard Cocotb Rules
include $(shell cocotb-config --makefiles)/Makefile.sim
