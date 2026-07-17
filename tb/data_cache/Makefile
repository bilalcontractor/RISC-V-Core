SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../packages/cpu_core_pkg.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_interface.sv
VERILOG_SOURCES += $(PWD)/../../packages/axi_lite_interface.sv
VERILOG_SOURCES += $(PWD)/../../src/data_cache.sv
VERILOG_SOURCES += $(PWD)/cache_axi_wrapper.sv

# The flat-signal wrapper, so cocotbext-axi can attach an AxiRam to the cache.
TOPLEVEL = cache_axi_wrapper
MODULE = test_data_cache

EXTRA_ARGS += --trace --trace-structs
# The debug taps (set_ptr_out[6:0]) are intentionally wider than the 3-bit
# set_ptr, so demote verilator's width warnings instead of erroring out.
EXTRA_ARGS += -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC

include $(shell cocotb-config --makefiles)/Makefile.sim
