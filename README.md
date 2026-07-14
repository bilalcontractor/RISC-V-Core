A single-cycle RISC-V (RV32I) CPU written from scratch in SystemVerilog following the HolyCore course, with per-module testbenches driven by [cocotb](https://www.cocotb.org/) and
[Verilator](https://www.veripool.org/verilator/). The core now talks to memory
through an **AXI4 bus** behind a pair of **direct-mapped write-back caches** (one
for instructions, one for data) merged by an **arbiter**. It also features an **AXI-Lite MMIO bus** for routing non-cacheable accesses bypassing the data cache.

The core runs **real compiled programs**: hand-written RISC-V assembly and full
**C** (compiled with GCC + newlib, `printf` and all) execute end-to-end on the
RTL and print to a simulated UART. It also passes the **RV32I
[RISCOF](https://github.com/riscv-software-src/riscof) / riscv-arch-test
compliance suite**, signature-diffed against the Sail reference model.

## Architecture

The core is a classic single-cycle datapath: every instruction fetches,
decodes, executes, accesses memory, and writes back within one clock cycle —
except that a cache miss now stalls the whole core (PC frozen, register write
squashed) until the line is refilled over AXI.

```
        +-----+     +-------------+     +---------+    +-----+    +-----+    +---------+
  pc -->| I$  |-->  | control +   |---> | regfile |--->| alu |--->| LSU |--->|   D$    |
        +-----+     | signext     |     +---------+    +-----+    +-----+    +---------+
          ^         +-------------+          |            |          ^           |   |
          |                                  +------------+----------+--- write-back mux
          |                                                  (LSU = byte_enable_decoder + reader)
          +--------------- pc_next (pc+4 / branch-jump target / jalr), frozen while stalled ----+

   I$ ─┐
       ├─► cache_arbiter ──AXI──► external memory   (I$ wins ties)
   D$ ─┘
       └─► AXI-Lite MMIO bus (bypassing cache for non-cacheable ranges)
```

The `LSU` (load/store unit) wraps the store-side byte-enable decoder and the
load-side reader around the data cache. Both caches master their own AXI
interface; the `cache_arbiter` muxes them onto the single external bus exposed
at the top level. The data cache additionally masters an AXI-Lite bus for MMIO.

| Module                 | File                          | Role                                                        |
|------------------------|-------------------------------|-------------------------------------------------------------|
| `cpu`                  | `src/cpu.sv`                  | Top level: PC, wiring, muxes, the two caches + arbiter; exposes external `axi_interface.master` and `axi_lite_interface.master` (MMIO) ports |
| `control`              | `src/control.sv`              | Main decoder + ALU decoder + branch resolution              |
| `alu`                  | `src/alu.sv`                  | ADD / SUB / AND / OR / XOR / SLT(U) / shifts, plus `zero` and `alu_last` flags |
| `regfile`              | `src/regfile.sv`              | 32 × 32-bit register file (2 read ports, 1 write port)      |
| `csrfile`              | `src/csrfile.sv`              | Holds CSRs including non-cacheable range bounds and cache flush flag |
| `signext`              | `src/signext.sv`              | Immediate extraction/sign-extension for I/S/B/J/U formats   |
| `byte_enable_decoder`  | `src/byte_enable_decoder.sv`  | Store path: picks the byte/half lane and shifts the register data into place, emitting the `byte_enable` mask |
| `reader`               | `src/reader.sv`               | Load path: the inverse — shifts the selected lane down to bit 0, then sign- or zero-extends it |
| `load_store_unit`      | `src/load_store_unit.sv`      | Thin wrapper bundling `byte_enable_decoder` (stores) + `reader` (loads) into one unit around the data cache |
| `cache`                | `src/cache.sv`                | Direct-mapped, write-back, write-allocate cache with an AXI master FSM; used for I$ |
| `data_cache`           | `src/data_cache.sv`           | Direct-mapped, write-back cache that routes non-cacheable accesses (MMIO) to a dedicated AXI-Lite bus; used for D$ |
| `cache_arbiter`        | `src/cache_arbiter.sv`        | Combinational interconnect merging the I$ and D$ AXI buses onto one external port (instruction cache prioritised) |
| `memory`               | `src/memory.sv`               | Simple word/byte-addressable memory; no longer in the core datapath — kept as a behavioural model for the standalone testbenches |

Shared opcodes, func3/func7 encodings, the ALU/mux select enums, **and the cache
FSM state enum** live in the `cpu_core_pkg` package
(`packages/cpu_core_pkg.sv`), imported by every module so the datapath reads in
named constants rather than raw bit patterns. The AXI bus itself is a
SystemVerilog `interface` with `master`/`slave` modports in
`packages/axi_interface.sv`.

## Memory subsystem (AXI + caches)

The single-cycle core used to read instruction and data memory combinationally
from two `memory` instances. Those have been replaced by a proper memory
hierarchy:

**AXI4 interface (`packages/axi_interface.sv`).** A full AXI4 bundle — five
channels (write address / write data / write response / read address / read
data) — packaged as a SystemVerilog `interface` with `master` and `slave`
modports, so a single named connection carries the whole bus and direction is
enforced by the modport.

**Cache (`src/cache.sv`).** A direct-mapped, write-back, write-allocate cache
(parameterised: `CACHE_SIZE = 128` bytes, `NUM_SETS = 16`, so 1 way, 8
words/line by default). Each line carries `DIRTY | VALID | TAG | data`. The
address is sliced into `tag = addr[31:9]`, `set = addr[8:5]`, `word =
addr[4:2]`. Behaviour:

- **Hit read** returns the word combinationally. **Hit write** does a masked,
  per-byte update using the incoming `byte_enable` and marks the set dirty.
- **Miss** triggers a refill: if the resident line is dirty it is first
  **written back** to memory as an AXI burst, then the requested line is fetched
  as a burst and stamped with the new tag. A 6-state AXI master FSM (`IDLE`,
  `SENDING_WRITE_REQUEST`, `SENDING_WRITE_DATA`, `WAITING_WRITE_RECIEVE`,
  `SENDING_READ_REQUEST`, `RECIEVING_READ_DATA`) drives the handshakes; bursts
  are fixed-length INCR (`arlen`/`awlen = WORDS_PER_LINE-1`, 4-byte beats).
- **`cache_stall`** is asserted on a fresh miss and held throughout the
  miss-handling FSM, which is what stalls the core.
- **`csr_flush_order`** is an input that forces a write-back of the current line
  (a hook for the future Zicsr extension); it is wired to `0` in the core for
  now.
- **`cache_state`** is exported so the arbiter can see whether the cache wants
  the bus (anything other than `IDLE`).

**Arbiter (`src/cache_arbiter.sv`).** Purely combinational. It looks like
private memory (an AXI *slave*) to each cache and is the single AXI *master* to
the outside world. It splices whichever cache currently wants the bus onto the
external port; if both want it, the **instruction cache wins** (it's checked
first). Because a cache stays non-`IDLE` for the duration of its burst, the
connection is held for the whole transaction — no mid-burst switching. When both
caches are `IDLE` the external bus is parked at safe zero defaults.

**Integration in `cpu.sv`.** The top level now instantiates an instruction
cache (read-only, addressed by the PC) and a data cache (driven by the
LSU/ALU), each with its own internal `axi_interface`, joined by the arbiter to
the one external `m_axi` port. The data cache also exposes an `m_axi_lite`
port for routing MMIO traffic (defined by CSR non-cacheable ranges) outside
the cache. A `global_stall = i_cache_stall | d_cache_stall` freezes the PC
and gates the register write so the in-flight instruction is simply retried
until both caches are ready.

## Instruction support

| Type | Instructions    | Status        |
|------|-----------------|---------------|
| I (load) | `lw` `lb` `lh` `lbu` `lhu` | ✅ implemented + tested |
| S    | `sw` `sb` `sh`  | ✅ implemented + tested |
| R    | `add` `sub` `and` `or` `xor` `sll` `srl` `sra` `slt` `sltu` | ✅ implemented + tested |
| I (ALU) | `addi` `andi` `ori` `xori` `slti` `sltiu` `slli` `srli` `srai` | ✅ implemented + tested |
| U    | `lui` `auipc`   | ✅ implemented + tested |
| J    | `jal` `jalr`    | ✅ implemented + tested |
| B    | `beq` `bne` `blt` `bge` `bltu` `bgeu` | ✅ implemented + tested |
| SYSTEM | `fence` (nop), Zicsr `csrrw`/`csrrs`/… | ✅ CSR ops implemented + tested |

The full **RV32I base ISA** is implemented and passes the RV32I RISCOF /
riscv-arch-test compliance suite (see [Compliance testing](#compliance-testing-riscof)
below). RISCOF still flags the `M`-extension tests it runs by default, since
`mul`/`div` are not implemented yet — those are on the [roadmap](#roadmap).

**Sub-word loads/stores.** `sb`/`sh` and `lb`/`lh`/`lbu`/`lhu` reuse the normal
ALU address path; the byte/half handling lives in two mirror modules now bundled
into the `load_store_unit`. On a store, `byte_enable_decoder` reads the offset
from `alu_result[1:0]`, masks the register data to the bottom byte/half and
shifts it into the right lane, emitting a `byte_enable` mask the cache/memory
honours. On a load, `reader` does the inverse — shifts the addressed lane down to
bit 0 and sign-extends (`lb`/`lh`) or zero-extends (`lbu`/`lhu`) per `func3`. A
misaligned access makes the decoder emit a zero mask, which `reader` reports as
`valid = 0`; the CPU then squashes the register write so a bad load can't corrupt
the file.

**Branches.** The ALU exposes two branch flags: `zero` (whole result is 0, used
by `beq`/`bne`) and `alu_last` (result bit 0, used by `blt`/`bge`/`bltu`/`bgeu`
since the SLT operations deposit their comparison there). The control unit's
branch-resolution table maps `func3` to the right flag — with `func3[0]` acting
as the "invert the condition" bit — and gates it with the `branch` signal to form
`pc_source`.

**Jumps.** `jal` and `jalr` both link `pc + 4` into `rd` via the write-back mux.
`jal` targets `pc + imm` through the second adder (`pc_source = PC_TARGET`);
`jalr` instead targets the ALU result `rs1 + imm` (`pc_source = PC_ALU_RESULT`).

## Roadmap

The [HolyCore course](https://github.com/0BAB1/HOLY_CORE_COURSE) covers the
**full RV32I base ISA** (single-cycle edition) plus an AXI cache subsystem, the
**Zicsr** extension, and an FPGA-ready SoC (FPGA edition). The items below are
still on my plate because I haven't reached those stages yet — they are part of
the course, not beyond it.

**Done so far:** full RV32I single-cycle core, AXI4 interface, a direct-mapped
write-back cache, split I$/D$ with an arbiter, the LSU wrapper, CSR file
(Zicsr base), non-cacheable ranges (MMIO) via AXI-Lite, full CPU-level AXI
testbenches, a GCC/newlib toolchain flow that runs real assembly and C on the
core through a simulated UART, and RV32I RISCOF / riscv-arch-test compliance
against the Sail reference model.

**Remaining course material**

- Complete Zicsr: Add remaining CSR instructions/registers if any
- FPGA-ready SoC wrapper (FPGA edition)

**Beyond the course**

- Cache improvements: set-associativity (currently 1-way / direct-mapped)
- M extension: `mul` `mulh` `div` `rem` (needs a multiply/divide unit)
- Other extensions: atomics (A), compressed (C), floating point (F/D)
- Pipelining the single-cycle core (IF/ID/EX/MEM/WB) with hazard handling

Each new instruction generally touches three places: the immediate format in
`signext.sv`, the decode + ALU-op mapping in `control.sv`, and the operation
itself in `alu.sv` — with any new encodings added to `cpu_core_pkg.sv` first, and
a focused cocotb test under `tb/`. Sub-word memory ops additionally touch
`byte_enable_decoder.sv` (stores) and `reader.sv` (loads).

## Repository layout

```
src/                SystemVerilog source for each module
tb/                 cocotb testbenches, one directory per module (each with a Makefile)
  cpu/              full-CPU TB: instruction regression + whole-program flows
    programs/       assembly / C sources and their assembled hex images
    runtime/        build scripts (build_asm.sh, build_c.sh), crt0.s, syscalls.c, linker scripts
packages/           shared SystemVerilog packages (cpu_core_pkg, axi_interface, axi_lite_interface)
riscof/             RISCOF compliance harness (core DUT plugin, sail reference, arch-test suite)
venv/               Python virtual environment for cocotb (gitignored)
```

## Running the tests

Requirements: [Verilator](https://www.veripool.org/verilator/) and Python 3.12+.
The cache and arbiter testbenches additionally need
[`cocotbext-axi`](https://github.com/alexforencich/cocotbext-axi), which
provides the `AxiRam` / `AxiMaster` bus models they attach to.

```bash
# one-time: set up the cocotb environment
python3 -m venv venv
source venv/bin/activate
pip install cocotb cocotbext-axi

# run a module's testbench
cd tb/alu
make

# clean build artifacts
make clean
```

Each `tb/<module>/` directory contains a `Makefile` and a `test_<module>.py`.
Available targets: `alu`, `control`, `regfile`, `signext`, `memory`,
`byte_enable_decoder`, `reader`, `cache`, `cache_arbiter`, and `cpu`. Waveforms
are emitted as `.vcd` files (open with GTKWave).

**AXI test wrappers.** `cocotbext-axi`'s bus models need *flat* top-level AXI
signals, but the cache and arbiter expose SystemVerilog `axi_interface` ports.
So those two testbenches build against a small wrapper that splits the interface
into flat signals and surfaces the debug taps:

- `tb/cache/cache_axi_wrapper.sv` — wraps a single `cache`, attaches an `AxiRam`
  as backing memory, and exposes the `cache_state` / `set_ptr` taps.
- `tb/cache_arbiter/arbiter_axi_wrapper.sv` — wraps the `cache_arbiter` with an
  `AxiRam` on the memory side and an `AxiMaster` standing in for each cache; the
  test drives the two `cache_state` inputs to exercise idle/active and
  read/write contention scenarios.

**CPU test wrapper.** The `tb/cpu/test_cpu.py` testbench fully integrates the CPU.
It uses a `test_harness.sv` wrapper that breaks out the `m_axi` and `m_axi_lite`
interfaces into flat signals, allowing `cocotbext-axi` to attach an `AxiRam` (for
main memory) and an AXI-Lite responder (for MMIO) directly to the core. The
full-CPU tests are split across two modules that share `sim_common.py` helpers:
`test_cpu.py` holds the hand-assembled instruction-level regression (runs on a
plain `make`), and `test_program.py` holds the whole-program flows (RISCOF
signature dump + free-running program runner, each skipped unless its env vars
are set).

## Running programs on the core

Beyond the per-instruction tests, the core runs whole compiled programs and
prints to a **simulated UART**. The UART is a Python coroutine (`uart_bridge` in
`sim_common.py`) that snoops the AXI-Lite MMIO bus: a program opens a
non-cacheable window via the CSRs, then stores characters to the UART TX
register (`0x2010`), which the bridge captures and prints. All of this still runs
through cocotb + Verilator on the RTL.

**Assembly.** Put a `.s` file in `tb/cpu/programs/`, assemble it, and free-run it:

```bash
cd tb/cpu
make asm ASM=hello                       # programs/hello.s  -> programs/hello_imemory.hex
make run HEX=programs/hello_imemory.hex   # prints only the program's UART output
```

`build_asm.sh` (in `runtime/`) drives `as -> ld -> objcopy -> hexdump` into the
flat little-endian hex image `init_memory()` loads. It uses the system
`riscv64-unknown-elf-` binutils by default (override `PREFIX` if yours differs).

**C.** Put a `.c` file in `tb/cpu/programs/` and build + run it in one step:

```bash
cd tb/cpu
make c C=hello_c                     # compile programs/hello_c.c and run it
make c C=hello_c MAX_CYCLES=200000   # raise the cycle budget for longer runs
```

`build_c.sh` links `crt0.s` + `syscalls.c` + your program against **newlib-nano**
so a real `printf` works (its `_write` retargets to the UART). This needs an
rv32i newlib toolchain — the scripts default to
`/home/bilal/riscv32i/bin/riscv32-unknown-elf-`; override `PREFIX` to point at
yours. `crt0.s` opens the MMIO window, zeroes `.bss`, and calls `main`; the
`-Os` / newlib-nano choices keep the image inside the linker map (see
`link_c.ld`).

## Compliance testing (RISCOF)

The `riscof/` directory wires the core into
[RISCOF](https://github.com/riscv-software-src/riscof), the official RISC-V
architectural test framework. It runs the
[riscv-arch-test](https://github.com/riscv-non-isa/riscv-arch-test) suite on both
the core and the **Sail** C reference model, then diffs the memory *signatures*
the two produce — a mismatch means the core diverged from the spec somewhere.

The core is plugged in as a RISCOF **DUT plugin** (`riscof/riscof_core/`) rather
than a standalone binary: instead of invoking an executable, the plugin compiles
each test `.S` to a hex image and runs the `tb/cpu` cocotb testbench
(`riscof_signature_test` in `test_program.py`), which boots the binary at
`0x8000_0000`, free-runs it to the `tohost` exit, and dumps the signature region.
Each run also emits a spike-style per-commit log (`dut.log`) so a failing test
can be root-caused with a plain diff against the reference model's log instead of
digging through waveforms.

The full **RV32I** suite passes. `M`-extension tests in the default suite still
fail, since `mul`/`div` aren't implemented yet.

```bash
# copy the template and point it at your checkout (config.ini is gitignored)
cp riscof/config.ini.example riscof/config.ini
# then edit config.ini, replacing <REPO_ROOT> with your absolute repo path
```

Running RISCOF additionally needs the `riscof` Python package, the `sail-riscv`
reference simulator, and an rv32 GCC toolchain (`riscv32-unknown-elf-*`) on
`PATH`.
