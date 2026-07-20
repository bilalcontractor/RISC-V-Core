import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random

# CSR addresses we run the generic read/write suite against.
# flush_cache lives at 0x7C0 (machine-mode custom RW region). Add more here later.
RW_REGS = [0x7C0]

# Machine-mode trap CSR addresses (mirrors csr_address_type in cpu_core_pkg).
CSR_MSTATUS = 0x300
CSR_MIE = 0x304
CSR_MEPC = 0x341
CSR_MCAUSE = 0x342
CSR_MTVAL = 0x343

# Exception causes (mcause[30:0] with mcause[31] == 0)
EXC_INSTR_ADDR_MISALIGNED = 0
EXC_ILLEGAL_INSTR = 2
EXC_BREAKPOINT = 3
EXC_LOAD_ADDR_MISALIGNED = 4
EXC_STORE_ADDR_MISALIGNED = 6
EXC_ECALL_M = 11

# Interrupt cause (mcause[30:0] with mcause[31] == 1)
INT_M_TIMER = 7

# mstatus bit positions
MSTATUS_MIE = 3
MSTATUS_MPIE = 7


async def reset(dut):
    """Pulse the active-low reset and clear the input stimulus."""
    dut.rst_n.value = 0
    dut.write_enable.value = 0
    dut.write_data.value = 0
    dut.address.value = 0
    dut.func3.value = 0

    # Trap-related stimulus
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.current_core_pc.value = 0
    dut.current_core_fetch_instr.value = 0
    set_exception_target_addr(dut, 0, 0)
    dut.mret.value = 0
    dut.exception.value = 0
    dut.exception_cause.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


def set_exception_target_addr(dut, second_adder_addr, alu_addr):
    """Drive the packed exception_target_addr struct.

    Depending on the simulator the struct is exposed either as sub-handles or
    flattened into one 64-bit vector ({second_adder_addr, alu_addr}).
    """
    try:
        dut.exception_target_addr.second_adder_addr.value = second_adder_addr
        dut.exception_target_addr.alu_addr.value = alu_addr
    except AttributeError:
        dut.exception_target_addr.value = (second_adder_addr << 32) | alu_addr


async def csr_write(dut, addr, value, func3=0b001):
    """Perform one CSR write and settle past the clock edge."""
    dut.write_enable.value = 1
    dut.address.value = addr
    dut.write_data.value = value
    dut.func3.value = func3
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    dut.write_enable.value = 0


async def csr_read(dut, addr):
    """Combinationally read a CSR through the read mux."""
    dut.address.value = addr
    await Timer(1, unit="ns")
    return int(dut.read_data.value)


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


@cocotb.test()
async def test_interrupt_trap(dut):
    """An enabled+pending interrupt with mstatus.MIE set raises trap and logs mcause/mepc."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # A pending interrupt alone does not trap while mie / mstatus.MIE are clear
    dut.timer_interrupt.value = 1
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert dut.trap.value == 0, "trap fired with mie and mstatus.MIE clear"

    # Enable the timer interrupt in mie -- still masked by the global mstatus.MIE
    await csr_write(dut, CSR_MIE, 1 << INT_M_TIMER)
    assert dut.trap.value == 0, "trap fired with global mstatus.MIE clear"

    # Now set the global enable: the trap must assert combinationally
    dut.current_core_pc.value = 0x0000_1234
    await csr_write(dut, CSR_MSTATUS, 1 << MSTATUS_MIE)
    assert dut.trap.value == 1, "trap did not fire for an enabled+pending interrupt"

    # The trap edge latches mepc and mcause
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert await csr_read(dut, CSR_MEPC) == 0x0000_1234
    assert await csr_read(dut, CSR_MCAUSE) == (1 << 31) | INT_M_TIMER


@cocotb.test()
async def test_mstatus_save_restore(dut):
    """Trap entry does MPIE=MIE, MIE=0; mret does MIE=MPIE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    dut.timer_interrupt.value = 1
    await csr_write(dut, CSR_MIE, 1 << INT_M_TIMER)
    await csr_write(dut, CSR_MSTATUS, 1 << MSTATUS_MIE)

    mstatus = await csr_read(dut, CSR_MSTATUS)
    assert (mstatus >> MSTATUS_MIE) & 1 == 1
    assert dut.trap.value == 1

    # Trap entry: MPIE takes the old MIE, MIE is cleared to mask nested traps
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    mstatus = await csr_read(dut, CSR_MSTATUS)
    assert (mstatus >> MSTATUS_MIE) & 1 == 0, "MIE not cleared on trap entry"
    assert (mstatus >> MSTATUS_MPIE) & 1 == 1, "MPIE did not capture the old MIE"

    # mret: MIE is restored from MPIE
    dut.mret.value = 1
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    dut.mret.value = 0
    mstatus = await csr_read(dut, CSR_MSTATUS)
    assert (mstatus >> MSTATUS_MIE) & 1 == 1, "MIE not restored from MPIE on mret"


@cocotb.test()
async def test_exception_trap_and_mtval(dut):
    """Exceptions trap regardless of mstatus.MIE and latch the right mcause/mtval."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    PC = 0x0000_4000
    INSTR = 0xDEAD_BEEF
    BRANCH_TARGET = 0x0000_5002  # second adder result (misaligned jump/branch)
    ALU_ADDR = 0x0000_6001       # ALU result (misaligned load/store)

    # (cause, expected mtval)
    cases = [
        (EXC_INSTR_ADDR_MISALIGNED, BRANCH_TARGET),
        (EXC_ILLEGAL_INSTR, INSTR),
        (EXC_LOAD_ADDR_MISALIGNED, ALU_ADDR),
        (EXC_STORE_ADDR_MISALIGNED, ALU_ADDR),
        (EXC_BREAKPOINT, PC),
        (EXC_ECALL_M, 0),
    ]

    for cause, expected_mtval in cases:
        await reset(dut)

        dut.current_core_pc.value = PC
        dut.current_core_fetch_instr.value = INSTR
        set_exception_target_addr(dut, BRANCH_TARGET, ALU_ADDR)

        # No interrupts enabled at all -- the exception alone must raise trap
        dut.exception.value = 1
        dut.exception_cause.value = cause
        await Timer(1, unit="ns")
        assert dut.trap.value == 1, f"exception cause {cause} did not raise trap"

        await RisingEdge(dut.clk)
        await Timer(2, unit="ns")
        dut.exception.value = 0

        # mcause[31] == 0 marks an exception rather than an interrupt
        assert await csr_read(dut, CSR_MCAUSE) == cause, (
            f"cause {cause}: got mcause={await csr_read(dut, CSR_MCAUSE):08X}"
        )
        assert await csr_read(dut, CSR_MEPC) == PC
        assert await csr_read(dut, CSR_MTVAL) == expected_mtval, (
            f"cause {cause}: got mtval={await csr_read(dut, CSR_MTVAL):08X} "
            f"exp={expected_mtval:08X}"
        )
