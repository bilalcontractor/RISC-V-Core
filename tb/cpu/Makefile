# Makefile

# 1. Define the Simulator
# We set the default to 'verilator' so you don't have to type it every time.
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# 2. Define the Paths to your Source Code
# $(PWD) is the current folder. We go up two levels to find the 'rtl' folder.
VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_interface.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_lite_interface.sv
VERILOG_SOURCES += $(PWD)/../../src/cpu.sv
VERILOG_SOURCES += $(PWD)/../../src/control.sv
VERILOG_SOURCES += $(PWD)/../../src/regfile.sv
VERILOG_SOURCES += $(PWD)/../../src/signext.sv
VERILOG_SOURCES += $(PWD)/../../src/alu.sv
VERILOG_SOURCES += $(PWD)/../../src/byte_enable_decoder.sv
VERILOG_SOURCES += $(PWD)/../../src/reader.sv
VERILOG_SOURCES += $(PWD)/../../src/load_store_unit.sv
VERILOG_SOURCES += $(PWD)/../../src/csrfile.sv
# Memory is no longer a CPU submodule: the caches + arbiter now front a single
# external AXI memory (an AxiRam in the testbench), so we pull those in instead.
VERILOG_SOURCES += $(PWD)/../../src/cache.sv
VERILOG_SOURCES += $(PWD)/../../src/data_cache.sv
VERILOG_SOURCES += $(PWD)/../../src/cache_arbiter.sv
# The flat-signal harness, so cocotbext-axi can attach an AxiRam to the CPU bus.
VERILOG_SOURCES += $(PWD)/test_harness.sv

# 3. Define the Top-Level Module
# The flat-signal harness that wraps the CPU and exposes its m_axi bus flat.
TOPLEVEL = test_harness

# 4. Define the Python Test Module
# This is the name of your python file WITHOUT the .py extension
# e.g. if your file is "test_module1.py", put "test_module1" here.
MODULE = test_cpu

# 5. Enable Waveforms (Trace)
# Verilator is fast but lazy; it won't create waveforms unless we force it.
# This creates a .vcd file you can open in GTKWave.
EXTRA_ARGS += --trace --trace-structs

# 6. Include the Standard Cocotb Rules
# This magic line finds where Cocotb is installed and loads all the hard work for you.
include $(shell cocotb-config --makefiles)/Makefile.sim