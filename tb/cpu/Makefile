# Makefile

# Define the Simulator
# We set the default to 'verilator' so you don't have to type it every time.
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# Retired-instruction budget for `make run` (run_program_test stops early when
# the PC parks). The 20000 default suits short .s files; C programs that call
# printf need more, e.g. `make run HEX=hello_c MAX_CYCLES=80000`.
MAX_CYCLES ?= 20000

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

# The bare-metal software project: sources in software/src/, the runtime (crt0,
# syscalls, linker scripts) in software/runtime/, and the build scripts at its
# top level. It's a separate thing from this testbench - these targets are just
# the simulator entry point into it.
SW := $(PWD)/../../software

# Assemble and free-run an arbitrary .s file, no Python/test changes needed.
# Everything still runs through cocotb+Verilator, but `run` prints ONLY the
# program's UART output - none of cocotb's INFO/WARNING logging or the results
# table. It re-enters this Makefile with a single TESTCASE and seds out just
# the text between the program's banners.
#   make asm ASM=hello      -> assembles software/src/hello.s
#   make run HEX=hello      -> runs it, prints whatever hits the UART
#                              (no assertion - see run_program_test)
.PHONY: asm
asm:
	@test -n "$(ASM)" || (echo "usage: make asm ASM=<name>   (expects software/src/<name>.s)" >&2; exit 1)
	@$(SW)/build_asm.sh $(ASM)

# HEX takes either a bare program name (resolved to software/src/<name>_imemory.hex,
# the common case) or a path to any hex image - the latter keeps `run` usable for
# images built outside software/, e.g. RISCOF's. A path is anything with a '/'.
#
# HEX_PATH must reach the sub-make as a command-line variable, not a shell prefix:
# `make run HEX=hello_c` makes HEX a command-line override, which outranks any env
# var we set on the recipe and would push the unresolved name through to the test.
# A command-line var on the sub-make's own line outranks it back, and make exports
# command-line vars to recipes for us.
HEX_PATH = $(if $(findstring /,$(HEX)),$(HEX),$(SW)/src/$(HEX)_imemory.hex)

.PHONY: run
run:
	@test -n "$(HEX)" || (echo "usage: make run HEX=<name>   (or HEX=<path/to/foo_imemory.hex>)" >&2; exit 1)
	@test -f "$(HEX_PATH)" || (echo "no such hex image: $(HEX_PATH)" >&2; exit 1)
	@COCOTB_LOG_LEVEL=WARNING $(MAKE) -s TESTCASE=run_program_test HEX=$(HEX_PATH) MAX_CYCLES=$(MAX_CYCLES) 2>&1 \
		| sed -n -e '/=== HOLY CORE UART OUTPUT ===/,/=== END UART OUTPUT ===/p' \
		         -e '/=== STATS ===/,/=== END STATS ===/p' \
		| grep -v '==='

# Compile a C program with the rv32i toolchain and free-run it in one step - the
# C sibling of `asm`+`run`. software/build_c.sh links the runtime (crt0.s +
# syscalls.c) with software/src/<name>.c against newlib-nano, then the resulting
# hex goes straight to the `run` pipeline so you see only the program's UART output.
#   make c C=hello_c                    -> build software/src/hello_c.c and run it
#   make c C=hello_c MAX_CYCLES=200000  -> raise the cycle budget for longer runs
# C defaults to a larger MAX_CYCLES than .s files because newlib printf is slow;
# a command-line MAX_CYCLES=... still overrides this.
.PHONY: c
c: MAX_CYCLES = 80000
c:
	@test -n "$(C)" || (echo "usage: make c C=<name>   (expects software/src/<name>.c)" >&2; exit 1)
	@$(SW)/build_c.sh $(C)
	@$(MAKE) -s run HEX=$(C) MAX_CYCLES=$(MAX_CYCLES)