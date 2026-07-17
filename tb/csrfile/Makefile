SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../src/csrfile.sv

TOPLEVEL = csrfile
MODULE = test_csrfile

EXTRA_ARGS += --trace --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim
