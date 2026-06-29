# DATA CACHE TESTBENCH
#
# The data_cache is just cache.sv with one thing bolted on: a non-cacheable
# (MMIO) path that bypasses the cache and talks to an AXI-Lite slave. Every
# cacheable behaviour (miss/refill, hit, dirty write-back, write miss, the
# CSR-ordered flush) is identical to cache.sv and is already covered by
# tb/cache/test_cache.py, so we do NOT re-test it here.
#
# This testbench exercises only what data_cache adds on top of cache.sv:
#   * the non_cachable_base/limit window decode (is_non_cachable),
#   * the AXI-Lite write FSM (LITE_SENDING_WRITE_REQUEST -> _WRITE_DATA ->
#     _WAITING_WRITE_RECIEVE -> IDLE),
#   * the AXI-Lite read FSM (LITE_SENDING_READ_REQUEST -> _RECIEVING_READ_DATA
#     -> IDLE) and the forwarding of the returned word to the CPU,
#   * the axi_lite_complete pulse that masks cache_stall for one IDLE cycle.

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiBus, AxiRam, AxiLiteBus, AxiLiteRam

# Cache geometry, mirror of the RTL params (only needed to size the RAMs and to
# reason about the non-cacheable window granularity).
CACHE_SIZE = 128
NUM_SETS = 16

MEM_BYTES = 4096  # size of each backing RAM (full AXI + AXI-Lite)

# FSM state encodings; order must match cpu_core_pkg::cache_state_type
IDLE                       = 0
SENDING_WRITE_REQUEST      = 1
SENDING_WRITE_DATA         = 2
WAITING_WRITE_RECIEVE      = 3
SENDING_READ_REQUEST       = 4
RECIEVING_READ_DATA        = 5
LITE_SENDING_WRITE_REQUEST = 6
LITE_SENDING_WRITE_DATA    = 7
LITE_WAITING_WRITE_RECIEVE = 8
LITE_SENDING_READ_REQUEST  = 9
LITE_RECIEVING_READ_DATA   = 10

CPU_PERIOD = 10   # ns
AXI_PERIOD = 10   # ns, must be >= CPU_PERIOD
SETTLE = 1        # ns, let combinational signals propagate before sampling
DEADLOCK = 10000  # max cycles to wait on an AXI response


def golden_word(mem, addr):
    return int.from_bytes(mem[addr:addr + 4], byteorder="little")


def generate_random_bytes(length):
    return bytes(random.randint(0, 255) for _ in range(length))


async def settle():
    await Timer(SETTLE, units="ns")


async def tick_cpu(dut):
    # Advance one CPU clock (the cache data/write side runs on dut.clk).
    await RisingEdge(dut.clk)
    await settle()


async def tick_axi(dut):
    # Advance one AXI clock (the FSM and bursts run on dut.aclk).
    await RisingEdge(dut.aclk)
    await settle()


def assert_state(dut, expected, msg=""):
    got = int(dut.cpu_cache_state.value)
    assert got == expected, f"state={got} expected={expected} {msg}"


async def reset(dut):
    dut.rst_n.value = 0
    dut.cpu_read_enable.value = 0
    dut.cpu_write_enable.value = 0
    dut.cpu_csr_flush_order.value = 0
    dut.cpu_non_cachable_base.value = 0
    dut.cpu_non_cachable_limit.value = 0
    dut.cpu_address.value = 0
    dut.cpu_write_data.value = 0
    dut.cpu_byte_enable.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await settle()

    assert_state(dut, IDLE, "after reset")
    assert dut.cpu_cache_stall.value == 0


async def wait_lite_idle(dut):
    # After a lite transaction, axi_lite_complete stays high for one IDLE cycle
    # (masking cache_stall) then auto-clears. Wait for it so the next request
    # sees a real stall rather than the masked one.
    for _ in range(4):
        if int(dut.cache_system.axi_lite_complete.value) == 0 and dut.cpu_cache_stall.value == 0:
            return
        await tick_axi(dut)
    assert int(dut.cache_system.axi_lite_complete.value) == 0, "axi_lite_complete never cleared"



# TEST PHASES

async def test_window_decode(dut):
    """The non_cachable_base/limit pair selects the MMIO window. The decode
    works on address[31:9], so the window snaps to 512-byte (0x200) tags and
    limit is exclusive. Check the boundaries purely combinationally (no FSM
    activity, so no AXI traffic)."""
    dut.cpu_non_cachable_base.value = 0x0000_0800
    dut.cpu_non_cachable_limit.value = 0x0000_1000
    dut.cpu_read_enable.value = 0
    dut.cpu_write_enable.value = 0

    cases = [
        (0x07FC, 0, "just below base -> cacheable"),
        (0x0800, 1, "at base -> non-cacheable"),
        (0x0FFC, 1, "last word below limit -> non-cacheable"),
        (0x1000, 0, "at limit (exclusive) -> cacheable"),
    ]
    for addr, expected, msg in cases:
        dut.cpu_address.value = addr
        await settle()
        assert int(dut.cache_system.is_non_cachable.value) == expected, \
            f"addr={addr:#x}: {msg}"


async def test_lite_write(dut, lite_ram, lite_golden):
    """A write inside the MMIO window bypasses the cache and runs as a single
    AXI-Lite write: AW -> W -> B -> IDLE."""
    dut.cpu_non_cachable_base.value = 0x0000_0000
    dut.cpu_non_cachable_limit.value = 0x0000_0800
    dut.cpu_byte_enable.value = 0b1111
    await settle()

    wr_addr = 0x404
    assert 0x0 <= wr_addr < 0x800
    dut.cpu_address.value = wr_addr
    dut.cpu_write_enable.value = 1
    dut.cpu_read_enable.value = 0
    dut.cpu_write_data.value = 0xABCDABCD
    await settle()

    # A non-cacheable access stalls and steers the FSM to the lite write entry.
    assert dut.cpu_cache_stall.value == 1
    assert dut.cache_system.is_non_cachable.value == 1
    assert dut.cache_system.next_state.value == LITE_SENDING_WRITE_REQUEST

    await tick_axi(dut)  # enter the lite write FSM
    assert_state(dut, LITE_SENDING_WRITE_REQUEST)

    # Walk the lite write to completion, checking the data beat as it passes and
    # that we visit each expected state.
    saw_wdata = False
    saw_wait = False
    cycles = 0
    while int(dut.cpu_cache_state.value) != IDLE:
        state = int(dut.cpu_cache_state.value)
        if state == LITE_SENDING_WRITE_DATA and dut.axi_lite_wvalid.value == 1:
            assert dut.axi_lite_wdata.value == 0xABCDABCD
            saw_wdata = True
        if state == LITE_WAITING_WRITE_RECIEVE:
            saw_wait = True
        await tick_axi(dut)
        cycles += 1
        assert cycles < DEADLOCK, "lite write did not complete"
    assert saw_wdata, "lite write never drove its data beat"
    assert saw_wait, "lite write never waited on its B response"

    # The B response sets axi_lite_complete, which masks cache_stall for the
    # cycle we land back in IDLE.
    assert int(dut.cache_system.axi_lite_complete.value) == 1
    assert dut.cpu_cache_stall.value == 0

    # The word actually reached the lite RAM.
    assert lite_ram.read(wr_addr, 4) == (0xABCDABCD).to_bytes(4, "little")
    lite_golden[wr_addr:wr_addr + 4] = (0xABCDABCD).to_bytes(4, "little")

    dut.cpu_write_enable.value = 0
    await wait_lite_idle(dut)


async def test_lite_read(dut, lite_golden):
    """A read inside the MMIO window bypasses the cache as a single AXI-Lite
    read; the returned word is forwarded to the CPU."""
    rd_addr = 0x40C
    expected = golden_word(lite_golden, rd_addr)

    dut.cpu_address.value = rd_addr
    dut.cpu_write_enable.value = 0
    dut.cpu_read_enable.value = 1
    await settle()

    assert dut.cpu_cache_stall.value == 1
    assert dut.cache_system.is_non_cachable.value == 1
    assert dut.cache_system.next_state.value == LITE_SENDING_READ_REQUEST

    await tick_axi(dut)  # enter the lite read FSM
    assert_state(dut, LITE_SENDING_READ_REQUEST)

    # Walk the lite read to completion, checking the address as it passes and
    # that we visit the data-receive state.
    saw_araddr = False
    saw_rdata = False
    cycles = 0
    while int(dut.cpu_cache_state.value) != IDLE:
        state = int(dut.cpu_cache_state.value)
        if state == LITE_SENDING_READ_REQUEST and dut.axi_lite_arvalid.value == 1:
            assert dut.axi_lite_araddr.value == rd_addr
            saw_araddr = True
        if state == LITE_RECIEVING_READ_DATA:
            saw_rdata = True
        await tick_axi(dut)
        cycles += 1
        assert cycles < DEADLOCK, "lite read did not complete"
    assert saw_araddr, "lite read never drove its address"
    assert saw_rdata, "lite read never reached its data-receive state"

    # Back in IDLE the lite result is forwarded to the CPU (read_enable still high).
    await settle()
    assert int(dut.cpu_read_data.value) == expected
    assert int(dut.cache_system.axi_lite_read_result.value) == expected

    dut.cpu_read_enable.value = 0
    await wait_lite_idle(dut)


async def test_lite_write_readback(dut, lite_ram, lite_golden):
    """End-to-end through the lite path: write a fresh value to an MMIO address,
    then read it back and confirm the FSM round-trips the same word."""
    addr = 0x7F8
    value = 0x12345678
    assert 0x0 <= addr < 0x800

    # ---- write ----
    dut.cpu_address.value = addr
    dut.cpu_byte_enable.value = 0b1111
    dut.cpu_write_enable.value = 1
    dut.cpu_read_enable.value = 0
    dut.cpu_write_data.value = value
    await settle()
    assert dut.cache_system.next_state.value == LITE_SENDING_WRITE_REQUEST

    await tick_axi(dut)  # leave IDLE into the lite write FSM
    cycles = 0
    while int(dut.cpu_cache_state.value) != IDLE:
        await tick_axi(dut)
        cycles += 1
        assert cycles < DEADLOCK, "lite write-back write did not complete"

    assert lite_ram.read(addr, 4) == value.to_bytes(4, "little")
    lite_golden[addr:addr + 4] = value.to_bytes(4, "little")
    dut.cpu_write_enable.value = 0
    await wait_lite_idle(dut)

    # ---- read back ----
    dut.cpu_address.value = addr
    dut.cpu_read_enable.value = 1
    await settle()
    assert dut.cache_system.next_state.value == LITE_SENDING_READ_REQUEST

    await tick_axi(dut)  # leave IDLE into the lite read FSM
    cycles = 0
    while int(dut.cpu_cache_state.value) != IDLE:
        await tick_axi(dut)
        cycles += 1
        assert cycles < DEADLOCK, "lite write-back read did not complete"

    await settle()
    assert int(dut.cpu_read_data.value) == value, "lite read did not return the value we wrote"
    dut.cpu_read_enable.value = 0
    await wait_lite_idle(dut)


# TOP-LEVEL TEST

@cocotb.test()
async def main_test(dut):
    cocotb.start_soon(Clock(dut.clk, CPU_PERIOD, units="ns").start())
    cocotb.start_soon(Clock(dut.aclk, AXI_PERIOD, units="ns").start())

    # The full-AXI slave is never exercised on the non-cacheable path, but it is
    # kept attached so the cache's full-AXI master inputs are driven to defined
    # values (no Xs) throughout.
    AxiRam(AxiBus.from_prefix(dut, "axi"), dut.aclk, dut.rst_n,
           reset_active_level=False, size=MEM_BYTES)
    lite_ram = AxiLiteRam(AxiLiteBus.from_prefix(dut, "axi_lite"), dut.aclk, dut.rst_n,
                          reset_active_level=False, size=MEM_BYTES)

    # Seed the lite memory and keep a golden mirror.
    lite_seed = generate_random_bytes(MEM_BYTES)
    lite_ram.write(0, lite_seed)
    lite_golden = bytearray(lite_seed)

    await reset(dut)

    await test_window_decode(dut)
    await test_lite_write(dut, lite_ram, lite_golden)
    await test_lite_read(dut, lite_golden)
    await test_lite_write_readback(dut, lite_ram, lite_golden)

    dut._log.info("data_cache AXI-Lite FSM test passed")
