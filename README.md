# HolyCore

A single-cycle RISC-V (RV32I) CPU written from scratch in SystemVerilog, following the
[HolyCore course](https://github.com/0BAB1/HOLY_CORE_COURSE). Every module has its own
cocotb testbench running under Verilator.

The core talks to memory over a real **AXI4 bus** through split instruction/data caches,
runs **actual compiled programs** (assembly and C, `printf` and all) that print to a
simulated UART, and passes the **RV32I compliance suite** diffed against the Sail
reference model.

## How it works

Classic single-cycle datapath: fetch, decode, execute, memory, write-back all in one
clock. The one exception is a cache miss, which stalls everything (PC frozen, register
write squashed) until the line comes back over AXI.

```
        +-----+     +-------------+     +---------+    +-----+    +-----+    +---------+
  pc -->| I$  |-->  | control +   |---> | regfile |--->| alu |--->| LSU |--->|   D$    |
        +-----+     | signext     |     +---------+    +-----+    +-----+    +---------+
          ^         +-------------+          |            |          ^           |   |
          |                                  +------------+----------+--- write-back mux
          |
          +--------------- pc_next (pc+4 / branch target / jalr), frozen while stalled ---+

   I$ ─┐
       ├─► cache_arbiter ──AXI──► external memory   (I$ wins ties)
   D$ ─┘
       └─► AXI-Lite MMIO bus (non-cacheable ranges bypass the cache)
```

### Modules

| Module | File | Role |
|---|---|---|
| `cpu` | `src/cpu.sv` | Top level: PC, wiring, muxes, both caches + arbiter. Exposes the external AXI and AXI-Lite ports |
| `control` | `src/control.sv` | Main decoder, ALU decoder, branch resolution |
| `alu` | `src/alu.sv` | ADD/SUB/AND/OR/XOR/SLT(U)/shifts, plus the `zero` and `alu_last` flags |
| `regfile` | `src/regfile.sv` | 32 × 32-bit registers, 2 read ports, 1 write port |
| `csrfile` | `src/csrfile.sv` | CSRs: non-cacheable range bounds, cache flush flag, trap state |
| `signext` | `src/signext.sv` | Immediate extraction for I/S/B/J/U formats |
| `byte_enable_decoder` | `src/byte_enable_decoder.sv` | Store path: shifts data into the right lane, emits the byte mask |
| `reader` | `src/reader.sv` | Load path: the inverse, shifting down to bit 0 then sign/zero-extending |
| `load_store_unit` | `src/load_store_unit.sv` | Bundles the two above into one unit around the data cache |
| `cache` | `src/cache.sv` | Direct-mapped write-back write-allocate cache with an AXI master FSM (used as I$) |
| `data_cache` | `src/data_cache.sv` | Same, but routes non-cacheable accesses out to AXI-Lite (used as D$) |
| `cache_arbiter` | `src/cache_arbiter.sv` | Combinational mux putting I$ and D$ onto one external bus |
| `memory` | `src/memory.sv` | Behavioural memory model, no longer in the datapath but kept for the standalone testbenches |

Opcodes, func3/func7 encodings, mux/ALU select enums and the cache FSM states all live in
`packages/cpu_core_pkg.sv`, so the datapath reads in named constants instead of raw bit
patterns. The AXI bus is a SystemVerilog `interface` with `master`/`slave` modports
(`packages/axi_interface.sv`).

## Memory subsystem

The core originally read instruction and data memory combinationally from two `memory`
instances. That's been replaced by a real hierarchy.

**The cache** is direct-mapped, write-back and write-allocate, 128 bytes across 16 sets by
default, so 1 way of 8 words per line. Address slices into `tag = addr[31:9]`,
`set = addr[8:5]`, `word = addr[4:2]`, and each line carries `DIRTY | VALID | TAG | data`.

A hit reads combinationally; a hit write does a masked per-byte update and marks the set
dirty. A miss kicks off a refill: write the resident line back first if it's dirty, then
burst the new line in and stamp the tag. A 6-state FSM drives the AXI handshakes with
fixed-length INCR bursts. `cache_stall` goes high on a fresh miss and stays high for the
whole FSM run, and that's what freezes the core.

**The arbiter** is purely combinational. It looks like private memory (an AXI slave) to
each cache and is the single master facing the outside world, splicing whichever cache
wants the bus onto the external port. If both want it, the instruction cache wins. Since
a cache stays non-`IDLE` for its entire burst, the connection holds for the whole
transaction, so there's no mid-burst switching. When both are idle, the external bus parks
at zero.

In `cpu.sv`, `global_stall = i_cache_stall | d_cache_stall` freezes the PC and gates the
register write, so an in-flight instruction just gets retried until both caches are ready.

## Instruction support

The full RV32I base ISA is implemented and passes compliance.

| Type | Instructions |
|---|---|
| I (load) | `lw` `lb` `lh` `lbu` `lhu` |
| S | `sw` `sb` `sh` |
| R | `add` `sub` `and` `or` `xor` `sll` `srl` `sra` `slt` `sltu` |
| I (ALU) | `addi` `andi` `ori` `xori` `slti` `sltiu` `slli` `srli` `srai` |
| U | `lui` `auipc` |
| J | `jal` `jalr` |
| B | `beq` `bne` `blt` `bge` `bltu` `bgeu` |
| SYSTEM | `fence` (nop), Zicsr `csrrw`/`csrrs`/… |

A few details worth calling out:

**Sub-word loads/stores** reuse the normal ALU address path. On a store,
`byte_enable_decoder` takes the offset from `alu_result[1:0]`, masks the register data down
to a byte/half and shifts it into the right lane, emitting a mask the cache honours. On a
load, `reader` does the inverse. Misaligned accesses make the decoder emit a zero mask,
`reader` reports `valid = 0`, and the CPU squashes the register write, so a bad load can't
corrupt the file.

**Branches** ride on two ALU flags: `zero` (for `beq`/`bne`) and `alu_last`, the result's
bit 0, which is where the SLT ops deposit their comparison (for `blt`/`bge`/`bltu`/`bgeu`).
The control unit maps `func3` to the right flag, with `func3[0]` acting as an
invert-the-condition bit.

**Jumps** both link `pc + 4` into `rd`. `jal` targets `pc + imm` via the second adder;
`jalr` targets the ALU result `rs1 + imm`.

## Repository layout

```
src/          SystemVerilog source, one file per module
tb/           cocotb testbenches, one directory per module (each with a Makefile)
  cpu/        full-CPU TB: instruction regression + whole-program flows
software/     bare-metal programs the core runs (build_asm.sh, build_c.sh)
  src/        assembly / C sources and their assembled hex images
  runtime/    crt0.s, syscalls.c, linker scripts
packages/     shared packages (cpu_core_pkg, axi_interface, axi_lite_interface)
riscof/       RISCOF compliance harness (DUT plugin, sail reference, arch-test suite)
venv/         Python virtualenv for cocotb (gitignored)
```

## Running the tests

You'll need [Verilator](https://www.veripool.org/verilator/) and Python 3.12+. The cache
and arbiter tests also want [`cocotbext-axi`](https://github.com/alexforencich/cocotbext-axi)
for its `AxiRam` / `AxiMaster` bus models.

```bash
# one-time setup
python3 -m venv venv
source venv/bin/activate
pip install cocotb cocotbext-axi

# run a module's testbench
cd tb/alu
make          # make clean to wipe artifacts
```

Every `tb/<module>/` has a `Makefile` and a `test_<module>.py`. Targets: `alu`, `control`,
`regfile`, `signext`, `memory`, `byte_enable_decoder`, `reader`, `cache`, `cache_arbiter`,
`cpu`. Waveforms are emitted as `.vcd` files, which open in GTKWave.

**Why the wrappers?** `cocotbext-axi` needs flat top-level signals, but the cache and
arbiter expose `axi_interface` ports. So those tests build against a small shim that splits
the interface apart and surfaces the debug taps: `tb/cache/cache_axi_wrapper.sv` and
`tb/cache_arbiter/arbiter_axi_wrapper.sv`. Same idea for the CPU, where `test_harness.sv` breaks
out `m_axi` and `m_axi_lite` so an `AxiRam` and an AXI-Lite responder can attach directly.

The full-CPU tests are split across two files sharing `sim_common.py`. `test_cpu.py` is the
hand-assembled instruction-level regression (runs on a plain `make`); `test_program.py`
holds the whole-program flows, each skipped unless its env vars are set.

## Running programs on the core

The core runs whole compiled programs and prints to a simulated UART. The UART is a Python
coroutine (`uart_bridge` in `sim_common.py`) snooping the AXI-Lite MMIO bus. A program opens
a non-cacheable window via the CSRs and stores characters to the TX register at `0x2010`,
and the bridge prints what it sees. All still on the RTL, through cocotb + Verilator.

Programs live in `software/`, separate from the testbenches, but you drive them from
`tb/cpu` since that's where the simulator runs.

**Assembly.** Drop a `.s` in `software/src/`, then:

```bash
cd tb/cpu
make asm ASM=hello    # software/src/hello.s -> hello_imemory.hex
make run HEX=hello    # prints just the program's UART output
```

`build_asm.sh` runs `as -> ld -> objcopy -> hexdump` into the flat little-endian hex image
`init_memory()` loads, using the system `riscv64-unknown-elf-` binutils (override `PREFIX`
if yours differ). `HEX` takes a bare program name, or a path if it contains a `/`, which is
handy for images built outside `software/`.

**C.** Drop a `.c` in `software/src/`, then build and run in one step:

```bash
cd tb/cpu
make c C=hello_c                     # compile and run
make c C=hello_c MAX_CYCLES=200000   # more cycles for longer runs
```

`build_c.sh` links `crt0.s` + `syscalls.c` + your program against **newlib-nano**, so a real
`printf` works (`_write` retargets to the UART). This needs an rv32i newlib toolchain. The
scripts default to `/home/bilal/riscv32i/bin/riscv32-unknown-elf-`, so override `PREFIX` for
yours. `crt0.s` opens the MMIO window, zeroes `.bss`, and calls `main`. The `-Os` and
newlib-nano choices are what keep the image inside the linker map (see `link_c.ld`).

## Compliance testing

`riscof/` wires the core into [RISCOF](https://github.com/riscv-software-src/riscof), the
official RISC-V architectural test framework. It runs the
[riscv-arch-test](https://github.com/riscv-non-isa/riscv-arch-test) suite on both the core
and the **Sail** reference model, then diffs the memory signatures. A mismatch means the
core diverged from the spec somewhere.

The core plugs in as a RISCOF **DUT plugin** rather than a standalone binary. Instead of
invoking an executable, the plugin compiles each test `.S` to a hex image and runs the
`tb/cpu` cocotb testbench, which boots at `0x8000_0000`, free-runs to the `tohost` exit, and
dumps the signature region. Each run also emits a spike-style per-commit log (`dut.log`), so
a failing test can be root-caused with a plain diff against the reference log instead of
digging through waveforms.

The full **RV32I** suite passes. The `M`-extension tests in the default suite still fail,
since `mul`/`div` aren't implemented yet.

```bash
cp riscof/config.ini.example riscof/config.ini
# edit config.ini, replacing <REPO_ROOT> with your absolute repo path
```

Beyond the test deps above, this needs the `riscof` Python package, the `sail-riscv`
simulator, and an rv32 GCC toolchain on `PATH`.

## Roadmap

The course covers the full RV32I ISA, the AXI cache subsystem, Zicsr, and an FPGA-ready
SoC. The first group below is course material I simply haven't reached yet; the second is
where I want to take it afterwards.

**Done:** RV32I single-cycle core, AXI4 interface, direct-mapped write-back cache, split
I$/D$ with arbiter, LSU, CSR file, MMIO via AXI-Lite, full CPU-level AXI testbenches, a
GCC/newlib flow running real assembly and C, and RV32I compliance against Sail.

**Still in the course**

- Finish Zicsr. M-mode traps and interrupts are in progress in `csrfile`, still being
  integrated with the rest of the core
- FPGA-ready SoC wrapper

**Beyond it**

- Set-associative caches (currently 1-way)
- M extension: `mul` `mulh` `div` `rem`
- Atomics (A), compressed (C), floating point (F/D)
- Pipelining with hazard handling

A new instruction usually touches three places: the immediate format in `signext.sv`, the
decode + ALU-op mapping in `control.sv`, and the operation in `alu.sv`, plus any new
encodings in `cpu_core_pkg.sv` first and a cocotb test under `tb/`. Sub-word memory ops
also touch `byte_enable_decoder.sv` and `reader.sv`.
