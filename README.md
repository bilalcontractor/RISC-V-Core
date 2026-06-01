A single-cycle RISC-V (RV32I) CPU written from scratch in SystemVerilog following the HolyCore course, with per-module testbenches driven by [cocotb](https://www.cocotb.org/) and
[Verilator](https://www.veripool.org/verilator/).

## Architecture

The core is a classic single-cycle datapath: every instruction fetches,
decodes, executes, accesses memory, and writes back within one clock cycle.

```
        +----+      +-------------+     +---------+    +-----+    +-------------+
  pc -->|IMEM|--->  | control +   |---> | regfile |--->| alu |--->| data memory |
        +----+      | signext     |     +---------+    +-----+    +-------------+
          ^         +-------------+          |            |            |
          |                                  +-----------+-------------+
          +--------------------- pc_next (pc+4 or branch target) ------+
```

| Module        | File              | Role                                                        |
|---------------|-------------------|-------------------------------------------------------------|
| `cpu`         | `src/cpu.sv`      | Top level: PC, wiring, write-back / ALU-source muxes        |
| `control`     | `src/control.sv`  | Main decoder + ALU decoder + branch resolution              |
| `alu`         | `src/alu.sv`      | ADD / SUB / AND / OR / XOR / SLT(U) / shifts, plus `zero` and `alu_last` flags |
| `regfile`     | `src/regfile.sv`  | 32 × 32-bit register file (2 read ports, 1 write port)      |
| `signext`     | `src/signext.sv`  | Immediate extraction/sign-extension for I/S/B/J/U formats   |
| `memory`      | `src/memory.sv`   | Shared module used for both instruction and data memory     |

Instruction and data memory are each initialized from a `.hex` file
(`test_imemory.hex` / `test_dmemory.hex`) at the testbench working directory.

## Instruction support

| Type | Instructions    | Status        |
|------|-----------------|---------------|
| I (load) | `lw`        | ✅ implemented + tested |
| S    | `sw`            | ✅ implemented + tested |
| R    | `add` `sub` `and` `or` `xor` `sll` `srl` `sra` `slt` `sltu` | ✅ implemented + tested |
| I (ALU) | `addi` `andi` `ori` `xori` `slti` `sltiu` `slli` `srli` `srai` | ✅ implemented + tested |
| U    | `lui` `auipc`   | ✅ implemented + tested |
| J    | `jal`           | ✅ implemented + tested |
| B    | `beq` `blt`     | ✅ implemented + tested |
| B    | `bne` `bge` `bltu` `bgeu` | 🚧 fully decode/flag-wired, not yet tested |

The ALU exposes two branch flags: `zero` (whole result is 0, used by `beq`/`bne`)
and `alu_last` (result bit 0, used by `blt`/`bge`/`bltu`/`bgeu` since the SLT
operations deposit their comparison there). The control unit's branch-resolution
table maps `func3` to the right flag — with `func3[0]` acting as the "invert the
condition" bit — and gates it with the `branch` signal to form `pc_source`.

## Roadmap

The [HolyCore course](https://github.com/0BAB1/HOLY_CORE_COURSE) covers the
**full RV32I base ISA** (single-cycle edition) plus the **Zicsr** extension and
an FPGA-ready SoC (FPGA edition). The instructions below are still on my plate
because I haven't reached those stages yet — they are part of the course, not
beyond it.

**Remaining course material** (mostly decoder + immediate work, datapath largely exists)

- Branch tests: add cocotb cases for the already-wired `bne` `bge` `bltu` `bgeu`
- Jumps: add `jalr`
- Other loads/stores: `lb` `lh` `lbu` `lhu` `sb` `sh` (needs a load/store decoder)
- Zicsr: CSR instructions + a CSR register file (FPGA edition)

**Beyond the course** 

- M extension: `mul` `mulh` `div` `rem` (needs a multiply/divide unit)
- Other extensions: atomics (A), compressed (C), floating point (F/D)
- Pipelining the single-cycle core (IF/ID/EX/MEM/WB) with hazard handling

Each new instruction generally touches three places: the immediate format in
`signext.sv`, the decode + ALU-op mapping in `control.sv`, and the operation
itself in `alu.sv` — plus a focused cocotb test under `tb/`.

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
Swap `alu` for `control`, `regfile`, `signext`, `memory`, or `cpu` to run the
others. Waveforms are emitted as `.vcd` files (open with GTKWave).
