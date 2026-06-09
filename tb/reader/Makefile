# Makefile

# 1. Define the Simulator
# We set the default to 'verilator' so you don't have to type it every time.
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# 2. Define the Paths to your Source Code
# $(PWD) is the current folder. We go up two levels to find the 'rtl' folder.
# Change 'module1.sv' to whatever your actual SystemVerilog file is named.
VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../src/reader.sv

# 3. Define the Top-Level Module
# This is the actual name of the module inside your .sv file (e.g., "module memory (...)")
TOPLEVEL = reader

# 4. Define the Python Test Module
# This is the name of your python file WITHOUT the .py extension
# e.g. if your file is "test_module1.py", put "test_module1" here.
MODULE = test_reader

# 5. Enable Waveforms (Trace)
# Verilator is fast but lazy; it won't create waveforms unless we force it.
# This creates a .vcd file you can open in GTKWave.
EXTRA_ARGS += --trace --trace-structs

# 6. Include the Standard Cocotb Rules
# This magic line finds where Cocotb is installed and loads all the hard work for you.
include $(shell cocotb-config --makefiles)/Makefile.sim