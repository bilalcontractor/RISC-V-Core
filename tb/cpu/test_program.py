# Whole-program flows: these load a fully compiled binary (as opposed to
# test_cpu.py's small hand-assembled instruction stream) and free-run it to
# completion. Two flavors live here:
#
#   riscof_signature_test - boots into a RISCOF/riscv-arch-test binary linked
#     at 0x8000_0000, runs until the tohost-style exit condition, dumps the
#     signature region RISCOF diffs against the reference model, and (as a
#     debugging aid) emits a spike-style per-commit log (dut.log) so a failing
#     test can be root-caused with a plain diff against the reference model's
#     own log instead of hunting through waveforms.
#
#   run_program_test - free-runs an arbitrary assembled .s file and dumps
#     whatever hits the UART, with no signature/pass-fail assertion.
#
# Both need the full 4 GiB address space (the RISCOF convention entry point,
# 0x8000_0000, is well past test_cpu.py's small 16 KiB regression memory map).

import logging
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiBus, AxiRam, AxiLiteBus, AxiLiteRam

from sim_common import (
    CPU_PERIOD, AXI_PERIOD, MEM_BYTES,
    cpu_reset, init_memory, wait_fetch, tick, uart_bridge,
)

FULL_ADDR_SPACE = 2 ** 32


def format_gpr(idx):
    if idx < 10:
        return f"x{idx} "
    else:
        return f"x{idx}"


def format_commit_line(dut):
    """Build one spike-style `core 0: 3 ...` commit-log line for the
    instruction currently retiring, or None while the pipeline is stalled.
    Signal names are HolyCore's (cpu_system.*), translated from the generic
    course/reference example this was adapted from (which used core.stall,
    core.dest_reg, core.mem_write_enable)."""
    if dut.cpu_system.global_stall.value != 0:
        return None

    str_gpr = ""
    if dut.cpu_system.reg_write.value and dut.cpu_system.wb_valid.value:
        reg_id = dut.cpu_system.destination.value.integer
        if reg_id != 0:  # ignore x0
            reg_val = dut.cpu_system.write_back_data.value.integer
            str_gpr = f" {format_gpr(reg_id)} 0x{reg_val:08x}"

    str_lsu = ""
    if dut.cpu_system.mem_write.value:
        addr = dut.cpu_system.alu_result.value.integer
        data = dut.cpu_system.mem_write_data.value.integer
        str_lsu = f" mem 0x{addr:08x} 0x{data:08x}"
    elif dut.cpu_system.mem_read_enable.value:
        addr = dut.cpu_system.alu_result.value.integer
        data = dut.cpu_system.mem_read.value.integer
        str_lsu = f" 0x{addr:08x} (0x{data:08x})"

    pc = dut.cpu_system.pc.value.integer
    instr = dut.cpu_system.instruction.value.integer
    str_ifu = f" 0x{pc:08x} (0x{instr:08x})"

    return f"core 0: 3{str_ifu}{str_gpr}{str_lsu}"


@cocotb.test(skip=not os.environ.get("IHEX_PATH"))
async def riscof_signature_test(dut):
    """Boot a compiled riscv-arch-test binary at 0x8000_0000, free-run it to
    completion, dump the signature RISCOF diffs against the reference model,
    and log every commit to dut.log for waveform-free debugging.

    Skipped unless IHEX_PATH is set (and non-empty), so a plain `make` (full
    regression) never touches this - it only runs when the RISCOF plugin (or a
    manual invocation) provides IHEX_PATH/begin_signature/end_signature/write_tohost."""
    program_hex = os.environ["IHEX_PATH"]
    begin_signature = int(os.environ["begin_signature"], 16)
    end_signature = int(os.environ["end_signature"], 16)
    write_tohost = int(os.environ["write_tohost"], 16)

    cocotb.start_soon(Clock(dut.clk, CPU_PERIOD, units="ns").start())
    cocotb.start_soon(Clock(dut.clk, AXI_PERIOD, units="ns").start())

    # Full 4 GiB address space: riscv-arch-test binaries are linked for
    # 0x8000_0000 (the spike/sail-riscv convention), well past test_cpu.py's
    # small regression-test memory map. Both busses get the program: cacheable
    # accesses land on m_axi, but marking the whole space non-cachable below
    # (as the boot ROM does) routes all data loads/stores through m_axi_lite
    # instead - see test_mmio in test_cpu.py for the same routing.
    axi_ram = AxiRam(AxiBus.from_prefix(dut, "m_axi"), dut.clk, dut.rst_n,
                     size=FULL_ADDR_SPACE, reset_active_level=False)
    axi_lite_ram = AxiLiteRam(AxiLiteBus.from_prefix(dut, "m_axi_lite"), dut.clk, dut.rst_n,
                              size=FULL_ADDR_SPACE, reset_active_level=False)

    await cpu_reset(dut)

    # CPU resets at PC=0, but the test binary expects to start at 0x8000_0000.
    # Boot ROM: mark the whole address space non-cachable (so the signature
    # dump below sees committed memory, not a stale cache line), then jump.
    axi_ram.write(0x0, int("FFFFF3B7", 16).to_bytes(4, 'little'))   # lui x7, 0xFFFFF
    axi_ram.write(0x4, int("7C101073", 16).to_bytes(4, 'little'))   # csrrw x0, 0x7C1, x0  (non_cachable_base = 0)
    axi_ram.write(0x8, int("7C239073", 16).to_bytes(4, 'little'))   # csrrw x0, 0x7C2, x7  (non_cachable_limit = 0xFFFFF000)
    axi_ram.write(0xC, int("800000B7", 16).to_bytes(4, 'little'))   # lui x1, 0x80000
    axi_ram.write(0x10, int("00008067", 16).to_bytes(4, 'little'))  # jalr x0, 0(x1)
    await init_memory(axi_ram, program_hex, 0x80000000)
    await init_memory(axi_lite_ram, program_hex, 0x80000000)

    # Clear the commit log before simulation starts.
    with open("dut.log", "w"):
        pass

    while not dut.cpu_system.pc.value.integer >= write_tohost:
        await Timer(1, units="ps")  # let signals settle before sampling
        line = format_commit_line(dut)
        if line is not None:
            with open("dut.log", "a") as fd:
                fd.write(line + "\n")
        await RisingEdge(dut.clk)

    dump_dir = os.path.dirname(program_hex)
    dump_path = os.path.join(dump_dir, "DUT-core.signature")
    with open(dump_path, "w") as sign_file:
        for addr in range(begin_signature, end_signature, 4):
            word = int.from_bytes(axi_lite_ram.read(addr, 4), byteorder="little")
            sign_file.write("{:08x}\n".format(word))


@cocotb.test(skip="HEX" not in os.environ)
async def run_program_test(dut):
    """Free-run whatever hex image HEX points at and dump its UART output.
    No assertion is made about the output, so new .s files (assembled with
    build_asm.sh) need no changes here. The program is considered finished
    when the PC repeats across two retired instructions (i.e. it hit a
    `j <self>` park loop like hello.s's `done:`), or MAX_CYCLES retired
    instructions elapse, whichever comes first.

    Skipped unless HEX is set, so a plain `make` (full regression) doesn't
    fail on it - it only runs via `make run HEX=...`."""
    hexfile = os.environ.get("HEX")
    if not hexfile:
        raise RuntimeError(
            "Set HEX=<path/to/foo_imemory.hex>, e.g. `make run HEX=hello_imemory.hex`"
        )
    max_cycles = int(os.environ.get("MAX_CYCLES", "20000"))

    cocotb.start_soon(Clock(dut.clk, CPU_PERIOD, units="ns").start())
    cocotb.start_soon(Clock(dut.clk, AXI_PERIOD, units="ns").start())

    axi_ram = AxiRam(AxiBus.from_prefix(dut, "m_axi"), dut.clk, dut.rst_n,
                     size=MEM_BYTES, reset_active_level=False)
    axi_lite_ram = AxiLiteRam(AxiLiteBus.from_prefix(dut, "m_axi_lite"), dut.clk, dut.rst_n,
                              size=MEM_BYTES, reset_active_level=False)

    await cpu_reset(dut)
    await init_memory(axi_ram, hexfile, 0x0000)
    await wait_fetch(dut)

    logging.getLogger("cocotb.test_harness.m_axi_lite").setLevel(logging.WARNING)

    tx_capture = bytearray()
    cocotb.start_soon(uart_bridge(dut, tx_capture))

    prev_pc = None
    for _ in range(max_cycles):
        await tick(dut)
        pc = int(dut.cpu_system.pc.value)
        if pc == prev_pc:
            break
        prev_pc = pc

    # Banners bracket the raw UART text so the Makefile `run` target can sed
    # out exactly the program's output (see Makefile:57 run:).
    print("=== HOLY CORE UART OUTPUT ===")
    print(bytes(tx_capture).decode("ascii", "replace"), end="")
    print("\n=== END UART OUTPUT ===")
