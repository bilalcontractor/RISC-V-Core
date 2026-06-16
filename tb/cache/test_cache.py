# test_cache.py
#
# Standalone cocotb test for the 16-set direct-mapped cache.
# A cocotbext-axi AxiRam stands in for main memory; mem_golden mirrors it so we
# can check that write-backs land correctly. The single test walks four
# scenarios in order:
#   1. read miss  -> refill a clean empty line, check the AXI read burst
#   2. read hits  -> every word of that line returns without stalling
#   3. write hit + conflicting miss -> the dirty line is written back, then refilled
#   4. write miss -> a clean conflicting line refills before the write commits

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiBus, AxiRam

# Cache geometry, mirror of the RTL params
CACHE_SIZE = 128
NUM_SETS = 16
WORDS_PER_LINE = CACHE_SIZE // NUM_SETS  # 8 words / 32 bytes per line
LINE_BYTES = WORDS_PER_LINE * 4
BURST_LEN = WORDS_PER_LINE - 1  # value carried on ar/awlen

MEM_BYTES = 4096  # size of the backing AxiRam

# FSM state encodings, order must match cpu_core_pkg::cache_state_type
IDLE = 0
SENDING_WRITE_REQUEST = 1
SENDING_WRITE_DATA = 2
WAITING_WRITE_RECIEVE = 3
SENDING_READ_REQUEST = 4
RECIEVING_READ_DATA = 5

CPU_PERIOD = 10  # ns
AXI_PERIOD = 10  # ns, must be >= CPU_PERIOD
SETTLE = 1  # ns, let combinational signals propagate before sampling
DEADLOCK = 10000  # max cycles to wait on an AXI response before giving up


# An address splits as | TAG[31:9] | SET[8:5] | WORD[4:2] | BYTE[1:0] |.
# These helpers pull each field out so the tests read in cache terms, not bits.
def tag_of(addr):
    return addr >> 9


def set_of(addr):
    return (addr >> 5) & (NUM_SETS - 1)


def word_of(addr):
    return (addr >> 2) & (WORDS_PER_LINE - 1)


def line_base(addr):
    # Address of word 0 of the line this address lives in (its AXI burst base).
    return addr & ~(LINE_BYTES - 1)


def cache_word_index(addr):
    # Flat word index into the packed cache_data vector, i.e. address[8:2].
    return (addr >> 2) & (CACHE_SIZE - 1)


def golden_word(mem, addr):
    # The 32-bit word our software memory model holds at addr.
    return int.from_bytes(mem[addr:addr + 4], byteorder="little")


def generate_random_bytes(length):
    return bytes(random.randint(0, 255) for _ in range(length))


def read_cache_word(cache_data_handle, addr):
    # Pull the 32-bit word stored for addr out of the packed cache_data vector.
    # cache_data is packed [NUM_SETS-1:0][WORDS_PER_LINE-1:0][31:0], so word N
    # (= address[8:2]) sits at bits [N*32 +: 32]. Read the whole vector as an
    # int and shift the word out, which avoids any slice-direction issues.
    word = cache_word_index(addr)
    full = cache_data_handle.value.to_unsigned()
    return (full >> (word * 32)) & 0xFFFFFFFF


async def settle():
    # Let combinational signals (hit, read_data, stall...) propagate before we sample.
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
    # Compare the FSM state (exposed on the cpu_cache_state debug tap) to expected.
    got = int(dut.cpu_cache_state.value)
    assert got == expected, f"state={got} expected={expected} {msg}"


async def reset(dut):
    # Drive reset and confirm the cache comes up empty and idle.
    dut.rst_n.value = 0
    dut.cpu_read_enable.value = 0
    dut.cpu_write_enable.value = 0
    dut.cpu_csr_flush_order.value = 0
    dut.cpu_address.value = 0
    dut.cpu_write_data.value = 0
    dut.cpu_byte_enable.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await settle()

    assert_state(dut, IDLE, "after reset")
    assert dut.cpu_cache_stall.value == 0


async def wait_unstalled(dut):
    # After a miss returns to IDLE the registered seq_stall keeps cache_stall
    # high for one more cycle. Step (a few cycles, bounded) until it drops.
    for _ in range(4):
        if dut.cpu_cache_stall.value == 0:
            return
        await tick_cpu(dut)
    assert dut.cpu_cache_stall.value == 0, "stall did not clear after returning to IDLE"


async def run_read_burst(dut):
    # Walk a RECIEVING_READ_DATA refill: WORDS_PER_LINE beats, set_ptr counting
    # up, rlast only on the final beat, and the cache stalling the whole time.
    beat = 0
    while beat < WORDS_PER_LINE - 1:
        if dut.axi_rvalid.value == 1 and dut.axi_rready.value == 1:
            assert dut.cpu_set_ptr.value == beat
            assert dut.axi_rlast.value == 0
            beat += 1
        assert dut.cpu_cache_stall.value == 1
        await tick_axi(dut)

    # last beat carries rlast
    while not (dut.axi_rvalid.value == 1 and dut.axi_rready.value == 1):
        await tick_axi(dut)
    assert dut.axi_rlast.value == 1


async def run_write_burst(dut, mem_golden, base_addr):
    # Walk a SENDING_WRITE_DATA write-back, mirroring each word the cache sends
    # into the golden model so we can later assert memory == golden. Returns
    # once the final beat (wlast) has been accepted.
    beat = 0
    addr = base_addr
    while beat < WORDS_PER_LINE - 1:
        if dut.axi_wvalid.value == 1 and dut.axi_wready.value == 1:
            assert dut.cpu_set_ptr.value == beat
            assert dut.axi_wlast.value == 0
            mem_golden[addr:addr + 4] = int(dut.axi_wdata.value).to_bytes(4, "little")
            beat += 1
            addr += 4
        assert dut.cpu_cache_stall.value == 1
        await tick_axi(dut)

    # last beat carries wlast
    while not (dut.axi_wvalid.value == 1 and dut.axi_wready.value == 1):
        await tick_axi(dut)
    assert dut.axi_wlast.value == 1
    mem_golden[addr:addr + 4] = int(dut.axi_wdata.value).to_bytes(4, "little")


@cocotb.test()
async def main_test(dut):
    # System init: clocks, an AxiRam playing main memory, and a golden mirror of it.
    cocotb.start_soon(Clock(dut.clk, CPU_PERIOD, units="ns").start())
    cocotb.start_soon(Clock(dut.aclk, AXI_PERIOD, units="ns").start())

    axi_ram = AxiRam(AxiBus.from_prefix(dut, "axi"), dut.aclk, dut.rst_n,
                     reset_active_level=False, size=MEM_BYTES)

    seed_data = generate_random_bytes(MEM_BYTES)
    axi_ram.write(0, seed_data)
    mem_golden = bytearray(seed_data)

    await reset(dut)

    # Test 1: read miss, refill set 0 from the line at 0x000
    dut.cpu_address.value = 0x000
    dut.cpu_read_enable.value = 1
    await settle()
    assert dut.cpu_cache_stall.value == 1, "fresh read miss should stall"

    await tick_axi(dut)
    assert_state(dut, SENDING_READ_REQUEST)
    assert dut.axi_araddr.value == line_base(0x000)
    assert dut.axi_arlen.value == BURST_LEN
    assert dut.axi_arsize.value == 0b010  # 4 bytes/beat
    assert dut.axi_arburst.value == 0b01  # INCR
    assert dut.axi_arvalid.value == 1

    await tick_axi(dut)
    assert_state(dut, RECIEVING_READ_DATA)
    await run_read_burst(dut)

    await tick_axi(dut)
    assert_state(dut, IDLE)
    await wait_unstalled(dut)

    # Test 2: read hits, every word of the refilled line reads back with no stall
    for word in range(WORDS_PER_LINE):
        addr = 0x000 + word * 4
        dut.cpu_address.value = addr
        await settle()
        assert dut.cpu_cache_stall.value == 0, f"word {word} should hit"
        assert int(dut.cpu_read_data.value) == golden_word(mem_golden, addr)
        await tick_cpu(dut)

    # one line further is a different set, so it misses again
    dut.cpu_address.value = LINE_BYTES  # 0x020 -> set 1, empty
    await settle()
    assert dut.cpu_cache_stall.value == 1
    await tick_axi(dut)
    assert_state(dut, SENDING_READ_REQUEST)
    # drain that refill so we are back in a known IDLE state
    await tick_axi(dut)
    await run_read_burst(dut)
    await tick_axi(dut)
    assert_state(dut, IDLE)
    await wait_unstalled(dut)

    # Test 3: write hit makes set 0 dirty, then a same-set/different-tag miss
    # forces a write-back before the refill
    dut.cpu_read_enable.value = 0
    dut.cpu_address.value = 0x00C  # set 0, word 3
    dut.cpu_byte_enable.value = 0b0011  # halfword, only the low 2 byte lanes
    dut.cpu_write_enable.value = 1
    dut.cpu_write_data.value = 0xDEADBEEF
    await settle()
    assert dut.cpu_cache_stall.value == 0, "write hit should not stall"

    # byte_enable 0b0011 keeps the upper halfword and overwrites the lower one
    expected = golden_word(mem_golden, 0x00C)
    expected = (expected & 0xFFFF0000) | (0xDEADBEEF & 0x0000FFFF)

    await tick_cpu(dut)  # the write commits here
    dut.cpu_write_enable.value = 0
    await settle()
    assert read_cache_word(dut.cache_system.cache_data, 0x00C) == expected

    # 0x200 is set 0, tag 1, so it conflicts with the dirty tag-0 line
    conflict_addr = 0x200
    assert set_of(conflict_addr) == set_of(0x000) and tag_of(conflict_addr) != tag_of(0x000)
    dut.cpu_address.value = conflict_addr
    dut.cpu_read_enable.value = 1
    await settle()
    assert dut.cpu_cache_stall.value == 1

    await tick_axi(dut)
    assert_state(dut, SENDING_WRITE_REQUEST)
    assert dut.axi_awvalid.value == 1
    assert dut.axi_awaddr.value == line_base(0x000)  # evict the old tag-0 line
    assert dut.axi_awlen.value == BURST_LEN
    assert dut.axi_wstrb.value == 0b1111

    await tick_axi(dut)
    assert_state(dut, SENDING_WRITE_DATA)
    await run_write_burst(dut, mem_golden, base_addr=line_base(0x000))

    await tick_axi(dut)
    assert_state(dut, WAITING_WRITE_RECIEVE)
    # wait for the write response, with a deadlock guard
    cycles = 0
    while not (dut.axi_bvalid.value == 1):
        await tick_axi(dut)
        cycles += 1
        assert cycles < DEADLOCK, "write response deadlock"
    assert dut.axi_bresp.value == 0b00  # OKAY

    # memory must now match our golden model
    assert axi_ram.read(0, MEM_BYTES) == bytes(mem_golden)

    # write-back done, the refill for 0x200 follows
    await tick_axi(dut)
    assert_state(dut, SENDING_READ_REQUEST)
    assert dut.axi_araddr.value == line_base(conflict_addr)

    await tick_axi(dut)
    assert_state(dut, RECIEVING_READ_DATA)
    await run_read_burst(dut)
    await tick_axi(dut)
    assert_state(dut, IDLE)
    await wait_unstalled(dut)

    # Test 4: write miss on a clean conflicting line refills first, then writes
    # set 0 now holds tag 1 (clean), 0x008 is set 0, tag 0, so it misses clean
    write_addr = 0x008
    dut.cpu_address.value = write_addr
    dut.cpu_byte_enable.value = 0b1111
    dut.cpu_write_enable.value = 1
    dut.cpu_read_enable.value = 0
    dut.cpu_write_data.value = 0xFFFFFFFF
    await settle()
    assert dut.cpu_cache_stall.value == 1, "write miss should stall"

    await tick_axi(dut)
    assert_state(dut, SENDING_READ_REQUEST)  # clean line, no write-back, refill first
    assert dut.axi_araddr.value == line_base(write_addr)

    await tick_axi(dut)
    assert_state(dut, RECIEVING_READ_DATA)
    await run_read_burst(dut)
    await tick_axi(dut)
    assert_state(dut, IDLE)

    # the data must not be in the cache until the write actually commits
    assert read_cache_word(dut.cache_system.cache_data, write_addr) != 0xFFFFFFFF
    await tick_cpu(dut)  # write commits now
    dut.cpu_write_enable.value = 0
    await settle()
    assert read_cache_word(dut.cache_system.cache_data, write_addr) == 0xFFFFFFFF

    dut._log.info("cache test passed")
