# Makefile

# Define the Simulator
# We set the default to 'verilator' so you don't have to type it every time.
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# Define the Paths to your Source Code
VERILOG_SOURCES += $(wildcard $(PWD)/../../packages/*.sv)
VERILOG_SOURCES += $(wildcard $(PWD)/../../src/*.sv)
# The flat-signal harness, so cocotbext-axi can attach an AxiRam to the CPU bus.
VERILOG_SOURCES += $(PWD)/test_harness.sv

# Define the Top-Level Module
# The flat-signal harness that wraps the CPU and exposes its m_axi bus flat.
TOPLEVEL = test_harness

# Define the Python Test Module
# Comma-separated: test_cpu.py holds the instruction-level regression
# (cpu_insrt_test, always runs), test_program.py holds the whole-program flows
# (riscof_signature_test, run_program_test - both skip themselves unless their
# env vars are set, so a plain `make` only runs cpu_insrt_test).
MODULE = test_cpu,test_program

# Enable Waveforms (Trace)
# Verilator is fast but lazy; it won't create waveforms unless we force it.
# This creates a .vcd file you can open in GTKWave.
EXTRA_ARGS += --trace --trace-structs

# RISCOF signature-test inputs (test_program.py's riscof_signature_test).
# Left unset for a plain `make`: exporting an unset var still puts an empty
# string in the environment, and riscof_signature_test's skip= check treats
# that as "not provided" - it only runs when these are actually passed, e.g.
# `make IHEX_PATH=... begin_signature=... end_signature=... write_tohost=...`
export IHEX_PATH
export begin_signature
export end_signature
export write_tohost

# Include the Standard Cocotb Rules
# This magic line finds where Cocotb is installed and loads all the hard work for you.
include $(shell cocotb-config --makefiles)/Makefile.sim

# Assemble and free-run an arbitrary .s file, no Python/test changes needed.
# Everything still runs through cocotb+Verilator, but `run` prints ONLY the
# program's UART output - none of cocotb's INFO/WARNING logging or the results
# table. It re-enters this Makefile with a single TESTCASE and seds out just
# the text between the program's banners.
#   make asm ASM=hello              -> assembles hello.s to hello_imemory.hex
#   make run HEX=hello_imemory.hex  -> runs it, prints whatever hits the UART
#                                       (no assertion - see run_program_test)
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