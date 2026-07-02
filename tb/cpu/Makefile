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

# ---------------------------------------------------------------------------
# 7. Assemble and free-run an arbitrary .s file, no Python/test changes needed.
# Everything still runs through cocotb+Verilator, but `run` prints ONLY the
# program's UART output - none of cocotb's INFO/WARNING logging or the results
# table. It re-enters this Makefile with a single TESTCASE and seds out just
# the text between the program's banners.
#   make asm ASM=hello              -> assembles hello.s to hello_imemory.hex
#   make run HEX=hello_imemory.hex  -> runs it, prints whatever hits the UART
#                                       (no assertion - see run_program_test)
# ---------------------------------------------------------------------------
.PHONY: asm
asm:
	@test -n "$(ASM)" || (echo "usage: make asm ASM=<name>   (expects <name>.s)" >&2; exit 1)
	./build_asm.sh $(ASM)

.PHONY: run
run:
	@test -n "$(HEX)" || (echo "usage: make run HEX=<path/to/foo_imemory.hex>" >&2; exit 1)
	@COCOTB_LOG_LEVEL=WARNING TESTCASE=run_program_test HEX=$(HEX) $(MAKE) -s 2>&1 \
		| sed -n '/=== HOLY CORE UART OUTPUT ===/,/=== END UART OUTPUT ===/p' \
		| grep -v '==='