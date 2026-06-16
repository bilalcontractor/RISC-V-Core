# Standalone cocotb test for the cache arbiter (I$ + D$ -> one memory bus).
# A cocotbext-axi AxiRam stands in for main memory on the arbiter's master
# port; two AxiMasters stand in for the instruction and data caches on the
# slave ports. We drive the *_cache_state inputs by hand to tell the arbiter
# who wants the bus, then walk five scenarios in order:

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiBus, AxiRam, AxiMaster

# CACHE STATES CST (order must match cpu_core_pkg::cache_state_type)
IDLE                  = 0b000
SENDING_WRITE_REQUEST = 0b001
SENDING_WRITE_DATA    = 0b010
WAITING_WRITE_RECIEVE = 0b011
SENDING_READ_REQUEST  = 0b100
RECIEVING_READ_DATA   = 0b101

# A line is WORDS_PER_LINE (8) * 4 bytes = 32 bytes, which on the 32-bit bus is
# an 8-beat burst (ar/awlen = 7). Requesting 32 bytes makes cocotbext-axi emit
# that burst automatically. Line-aligned addresses keep each test on its own line.
LINE_BYTES = 32
# Distinct per-byte payloads so a mis-ordered or dropped beat is caught.
LINE_TEST = bytes(range(LINE_BYTES))  # 00 01 02 ... 1F
LINE_BEEF = b'beef' * 8               # 32 bytes
LINE_1234 = b'1234' * 8               # 32 bytes


@cocotb.test()
async def main_test(dut):
    PERIOD = 10
    MEM_SIZE = 4096
    cocotb.start_soon(Clock(dut.clk, PERIOD, units="ns").start())

    # memory on the master side
    axi_ram_slave = AxiRam(
        AxiBus.from_prefix(dut, "m_axi"),
        dut.clk,
        dut.rst_n,
        reset_active_level=False,
        size=MEM_SIZE
    )
    # the two caches on the slave side
    i_cache_master = AxiMaster(
        AxiBus.from_prefix(dut, "s_axi_instr"),
        dut.clk,
        dut.rst_n,
        reset_active_level=False
    )
    d_cache_master = AxiMaster(
        AxiBus.from_prefix(dut, "s_axi_data"),
        dut.clk,
        dut.rst_n,
        reset_active_level=False
    )

    # Release reset so the bus models start driving (active-low).
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    await RisingEdge(dut.clk)
    # init states to IDLE
    dut.d_cache_state.value = IDLE
    dut.i_cache_state.value = IDLE
    await Timer(1, units="ns")

    # SCENARIO 1 : ONLY THE DCACHE WRITES (full-line burst)

    dut.d_cache_state.value = SENDING_WRITE_REQUEST
    await Timer(1, units="ns")
    await d_cache_master.write(0x000, LINE_TEST)
    dut.d_cache_state.value = IDLE
    await Timer(1, units="ns")

    assert axi_ram_slave.read(0x000, LINE_BYTES) == LINE_TEST

    # SCENARIO 2 : ONLY THE ICACHE READS (full-line burst)

    dut.i_cache_state.value = SENDING_READ_REQUEST
    await Timer(1, units="ns")
    data = await i_cache_master.read(0x000, LINE_BYTES)
    dut.i_cache_state.value = IDLE
    await Timer(1, units="ns")

    assert data.data == LINE_TEST

    # SCENARIO 3 : ONLY THE DCACHE READS (full-line burst)

    dut.d_cache_state.value = SENDING_READ_REQUEST
    await Timer(1, units="ns")
    data = await d_cache_master.read(0x000, LINE_BYTES)
    dut.d_cache_state.value = IDLE
    await Timer(1, units="ns")

    assert data.data == LINE_TEST

    # SCENARIO 4 : BOTH DCACHE & ICACHE READS
    # Both ask at once: I$ wins. We service the I$ read first, drop it to
    # IDLE, and only then can the D$ read get through.

    dut.d_cache_state.value = SENDING_READ_REQUEST
    dut.i_cache_state.value = SENDING_READ_REQUEST
    await Timer(1, units="ns")
    data_i = await i_cache_master.read(0x000, LINE_BYTES)
    await Timer(1, units="ns")
    dut.i_cache_state.value = IDLE
    await Timer(1, units="ns")

    assert data_i.data == LINE_TEST

    data_d = await d_cache_master.read(0x000, LINE_BYTES)
    await Timer(1, units="ns")
    dut.d_cache_state.value = IDLE
    await Timer(1, units="ns")

    assert data_d.data == LINE_TEST

    # SCENARIO 5 : BOTH DCACHE & ICACHE WRITE (full-line bursts, separate lines)
    # Same priority rule on the write path: I$ writes its line first, then D$.

    dut.d_cache_state.value = SENDING_WRITE_REQUEST
    dut.i_cache_state.value = SENDING_WRITE_REQUEST
    await Timer(1, units="ns")
    await i_cache_master.write(0x020, LINE_BEEF)
    await Timer(1, units="ns")
    dut.i_cache_state.value = IDLE
    await Timer(1, units="ns")

    await d_cache_master.write(0x040, LINE_1234)
    await Timer(1, units="ns")
    dut.d_cache_state.value = IDLE
    await Timer(1, units="ns")

    # we verify both lines were well written
    assert axi_ram_slave.read(0x020, LINE_BYTES) == LINE_BEEF
    assert axi_ram_slave.read(0x040, LINE_BYTES) == LINE_1234
