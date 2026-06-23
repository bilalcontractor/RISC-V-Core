import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random

# CSR addresses we run the generic read/write suite against.
# flush_cache lives at 0x7C0 (machine-mode custom RW region). Add more here later.
RW_REGS = [0x7C0]


async def reset(dut):
    """Pulse the active-low reset and clear the input stimulus."""
    dut.rst_n.value = 0
    dut.write_enable.value = 0
    dut.write_data.value = 0
    dut.address.value = 0
    dut.func3.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


# Map each CSR address to its backing register handle (mirrors the RTL decode).
def get_csr_value(dut, addr):
    if addr == 0x7C0:
        return int(dut.flush_cache.value)
        # other CSRs in the future ...
    return 0


@cocotb.test()
async def test_csr_file(dut):
    """Generic per-CSR read / write / reset sweep."""
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    for addr in RW_REGS:
        # simple write that persists.
        # NB: flush_cache self-clears when bit0 is set (bit0 is the flush request),
        # so we use an even value here to test plain storage without tripping a flush.
        dut.write_enable.value = 1
        dut.write_data.value = 0xDEADBEEE
        dut.address.value = addr
        dut.func3.value = 0b001  # CSRRW
        await RisingEdge(dut.clk)
        await Timer(2, unit="ns")
        assert get_csr_value(dut, addr) == 0xDEADBEEE
        assert int(dut.read_data.value) == 0xDEADBEEE

        # nothing gets written while write_enable is low
        dut.write_enable.value = 0
        dut.write_data.value = 0x12345678
        await RisingEdge(dut.clk)
        await Timer(2, unit="ns")
        assert get_csr_value(dut, addr) == 0xDEADBEEE

        # randomized op stream (CSRRW / CSRRS / CSRRC and the no-op f3 codes)
        dut.write_enable.value = 1
        for _ in range(1000):
            await RisingEdge(dut.clk)
            await Timer(1, unit="ns")

            init = get_csr_value(dut, addr)
            wd = random.randint(0, 0xFFFFFFFF)
            f3 = random.randint(0b000, 0b111)
            dut.write_data.value = wd
            dut.func3.value = f3

            await RisingEdge(dut.clk)
            await Timer(2, unit="ns")

            # If bit0 of the current value is set, the CSR self-clears this cycle
            # (the flush pulse) and ignores the write, so the result is 0.
            if init & 1:
                expected = 0
            elif f3 in (0b000, 0b100):  # no CSR op -> writes 0
                expected = 0
            elif f3 in (0b001, 0b101):  # CSRRW : overwrite
                expected = wd
            elif f3 in (0b010, 0b110):  # CSRRS : set bits
                expected = init | wd
            else:                       # CSRRC (0b011, 0b111) : clear bits
                expected = init & (~wd & 0xFFFFFFFF)

            assert int(dut.read_data.value) == expected, (
                f"f3={f3:03b} init={init:08X} wd={wd:08X} "
                f"got={int(dut.read_data.value):08X} exp={expected:08X}"
            )

        # reset clears the CSR back to 0. First write some sample data...
        dut.write_enable.value = 1
        dut.write_data.value = 0xDEADBEEF
        dut.address.value = addr
        dut.func3.value = 0b001
        await RisingEdge(dut.clk)

        # ...then assert reset and confirm the CSR reads back 0
        await reset(dut)
        assert get_csr_value(dut, addr) == 0
        assert int(dut.read_data.value) == 0


@cocotb.test()
async def test_cache_control_behavior(dut):
    """flush_cache CSR: writing bit0 emits a single-cycle flush_cache_flag pulse."""
    # Custom CSRs behavior

    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # FLUSH CACHE CSR BEHAVIOR :
    # If this CSR's LSB is asserted, the module outputs 1 on the "flush" order
    # output for 1 cycle. It is automatically deasserted after a clock cycle.

    # After reset the flush request is idle
    assert dut.flush_cache_flag.value == 0

    # Setting every bit EXCEPT the LSB must not raise the flush flag
    dut.write_enable.value = 1
    dut.write_data.value = 0xFFFFFFFE
    dut.address.value = 0x7C0
    dut.func3.value = 0b001
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert int(dut.flush_cache.value) == 0xFFFFFFFE
    assert dut.flush_cache_flag.value == 0

    # Writing the LSB raises the flush flag for exactly one cycle
    dut.write_data.value = 0x00000001
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert dut.flush_cache_flag.value == 1
    assert int(dut.flush_cache.value) == 0x00000001

    # ...and it self-clears on the following cycle
    dut.write_enable.value = 0
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert dut.flush_cache_flag.value == 0
    assert int(dut.flush_cache.value) == 0x00000000

@cocotb.test()
async def test_non_cachable_range(dut):
    """non-cachable base/limit CSRs: plain storage, sticky, drive the output ports."""
    # base lives at 0x7C1, limit at 0x7C2 (machine-mode custom RW region)

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # After reset both the registers and their output ports read back 0
    assert int(dut.non_cachable_base.value) == 0
    assert int(dut.non_cachable_limit.value) == 0
    assert int(dut.non_cachable_base_address.value) == 0
    assert int(dut.non_cachable_limit_address.value) == 0

    # Write the base CSR (CSRRW). Value persists and is exposed on the output port.
    dut.write_enable.value = 1
    dut.write_data.value = 0x90000000
    dut.address.value = 0x7C1
    dut.func3.value = 0b001  # CSRRW
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert int(dut.non_cachable_base.value) == 0x90000000
    assert int(dut.non_cachable_base_address.value) == 0x90000000
    assert int(dut.read_data.value) == 0x90000000

    # Write the limit CSR (CSRRW). Independent of the base register.
    dut.write_data.value = 0x9FFFFFFF
    dut.address.value = 0x7C2
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert int(dut.non_cachable_limit.value) == 0x9FFFFFFF
    assert int(dut.non_cachable_limit_address.value) == 0x9FFFFFFF
    assert int(dut.read_data.value) == 0x9FFFFFFF
    # base is unchanged by the limit write
    assert int(dut.non_cachable_base.value) == 0x90000000

    # Unlike flush_cache, these are sticky: they hold while write_enable is low
    dut.write_enable.value = 0
    dut.write_data.value = 0x12345678
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert int(dut.non_cachable_base.value) == 0x90000000
    assert int(dut.non_cachable_limit.value) == 0x9FFFFFFF

    # reset clears both CSRs back to 0
    await reset(dut)
    assert int(dut.non_cachable_base.value) == 0
    assert int(dut.non_cachable_limit.value) == 0
