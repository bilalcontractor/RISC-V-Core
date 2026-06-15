A single-cycle RISC-V (RV32I) CPU written from scratch in SystemVerilog following the HolyCore course, with per-module testbenches driven by [cocotb](https://www.cocotb.org/) and
[Verilator](https://www.veripool.org/verilator/).

## Architecture

The core is a classic single-cycle datapath: every instruction fetches,
decodes, executes, accesses memory, and writes back within one clock cycle.

```
        +----+      +-------------+     +---------+    +-----+   +-----+   +-------------+   +--------+
  pc -->|IMEM|--->  | control +   |---> | regfile |--->| alu |-->| BED |-->| data memory |-->| reader |
        +----+      | signext     |     +---------+    +-----+   +-----+   +-------------+   +--------+
          ^         +-------------+          |            |                                       |
          |                                  +------------+------------ write-back mux -----------+
          +-------------------- pc_next (pc+4 / branch-jump target / jalr) ----------------------+
```

`BED` is the byte-enable decoder on the store path; `reader` is its mirror on
the load path (details under *Instruction support*).

| Module                 | File                          | Role                                                        |
|------------------------|-------------------------------|-------------------------------------------------------------|
| `cpu`                  | `src/cpu.sv`                  | Top level: PC, wiring, write-back / ALU-source / next-PC muxes |
| `control`              | `src/control.sv`              | Main decoder + ALU decoder + branch resolution              |
| `alu`                  | `src/alu.sv`                  | ADD / SUB / AND / OR / XOR / SLT(U) / shifts, plus `zero` and `alu_last` flags |
| `regfile`              | `src/regfile.sv`              | 32 × 32-bit register file (2 read ports, 1 write port)      |
| `signext`              | `src/signext.sv`              | Immediate extraction/sign-extension for I/S/B/J/U formats   |
| `byte_enable_decoder`  | `src/byte_enable_decoder.sv`  | Store path: picks the byte/half lane and shifts the register data into place, emitting the `byte_enable` mask |
| `reader`               | `src/reader.sv`               | Load path: the inverse — shifts the selected lane down to bit 0, then sign- or zero-extends it |
| `memory`               | `src/memory.sv`               | Shared module used for both instruction and data memory; honours `byte_enable` for sub-word writes |

Shared opcodes, func3/func7 encodings, and the ALU/mux select enums live in the
`cpu_core_pkg` package (`packages/cpu_core_pkg.sv`), imported by every module so
the datapath reads in named constants rather than raw bit patterns.

Instruction and data memory are each initialized from a `.hex` file
(`test_imemory.hex` / `test_dmemory.hex`) at the testbench working directory.

## Instruction support

| Type | Instructions    | Status        |
|------|-----------------|---------------|
| I (load) | `lw` `lb` `lh` `lbu` `lhu` | ✅ implemented + tested |
| S    | `sw` `sb` `sh`  | ✅ implemented + tested |
| R    | `add` `sub` `and` `or` `xor` `sll` `srl` `sra` `slt` `sltu` | ✅ implemented + tested |
| I (ALU) | `addi` `andi` `ori` `xori` `slti` `sltiu` `slli` `srli` `srai` | ✅ implemented + tested |
| U    | `lui` `auipc`   | ✅ implemented + tested |
| J    | `jal` `jalr`    | ✅ implemented + tested |
| B    | `beq` `blt`     | ✅ implemented + tested |
| B    | `bne` `bge` `bltu` `bgeu` | 🚧 fully decode/flag-wired, not yet tested |

With those, the full **RV32I base ISA** is implemented; only the four untested
branch variants are left to exercise.

**Sub-word loads/stores.** `sb`/`sh` and `lb`/`lh`/`lbu`/`lhu` reuse the normal
ALU address path; the byte/half handling is split into two mirror modules. On a
store, `byte_enable_decoder` reads the offset from `alu_result[1:0]`, masks the
register data to the bottom byte/half and shifts it into the right lane, emitting
a `byte_enable` mask the memory honours. On a load, `reader` does the inverse —
shifts the addressed lane down to bit 0 and sign-extends (`lb`/`lh`) or
zero-extends (`lbu`/`lhu`) per `func3`. A misaligned access makes the decoder
emit a zero mask, which `reader` reports as `valid = 0`; the CPU then squashes the
register write so a bad load can't corrupt the file.

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
**full RV32I base ISA** (single-cycle edition) plus the **Zicsr** extension and
an FPGA-ready SoC (FPGA edition). The instructions below are still on my plate
because I haven't reached those stages yet — they are part of the course, not
beyond it.

**Remaining course material**

- Zicsr: CSR instructions + a CSR register file (FPGA edition)
- FPGA-ready SoC wrapper (FPGA edition)

**Beyond the course** 

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
src/        SystemVerilog source for each module
tb/         cocotb testbenches, one directory per module (each with a Makefile)
packages/   shared SystemVerilog packages
venv/        Python virtual environment for cocotb (gitignored)
```

## Running the tests

Requirements: [Verilator](https://www.veripool.org/verilator/) and Python 3.12+.

```bash
# one-time: set up the cocotb environment
python3 -m venv venv
source venv/bin/activate
pip install cocotb

# run a module's testbench
cd tb/alu
make

# clean build artifacts
make clean
```

Each `tb/<module>/` directory contains a `Makefile` and a `test_<module>.py`.
Swap `alu` for `control`, `regfile`, `signext`, `memory`,
`byte_enable_decoder`, `reader`, or `cpu` to run the others. Waveforms are
emitted as `.vcd` files (open with GTKWave).
