SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_interface.sv
VERILOG_SOURCES += $(PWD)/../../src/cache_arbiter.sv
VERILOG_SOURCES += $(PWD)/arbiter_axi_wrapper.sv

# The flat-signal wrapper, so cocotbext-axi can attach the AxiRam + AxiMasters.
TOPLEVEL = arbiter_axi_wrapper
MODULE = test_cache_arbiter

EXTRA_ARGS += --trace --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim
