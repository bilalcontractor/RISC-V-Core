SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_interface.sv
VERILOG_SOURCES += $(PWD)/../../src/cache.sv
VERILOG_SOURCES += $(PWD)/cache_axi_wrapper.sv

# The flat-signal wrapper, so cocotbext-axi can attach an AxiRam to the cache.
TOPLEVEL = cache_axi_wrapper
MODULE = test_cache

EXTRA_ARGS += --trace --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim
