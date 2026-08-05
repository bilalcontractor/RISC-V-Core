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
CSR_MTVEC = 0x305
CSR_MSCRATCH = 0x340
CSR_MEPC = 0x341
CSR_MCAUSE = 0x342
CSR_MTVAL = 0x343
CSR_MIP = 0x344
CSR_MISA = 0x301
CSR_FLUSH_CACHE = 0x7C0
CSR_NON_CACHABLE_BASE = 0x7C1
CSR_NON_CACHABLE_LIMIT = 0x7C2

MAPPED_CSRS = [
    CSR_FLUSH_CACHE, CSR_NON_CACHABLE_BASE, CSR_NON_CACHABLE_LIMIT,
    CSR_MSTATUS, CSR_MISA, CSR_MIE, CSR_MIP, CSR_MTVEC,
    CSR_MSCRATCH, CSR_MEPC, CSR_MCAUSE, CSR_MTVAL,
]

# misa: MXL=1 (RV32) | bit 8 (I extension). Mirrors MISA_VALUE in cpu_core_pkg.
MISA_VALUE = 0x40000100

# Exception causes (mcause[30:0] with mcause[31] == 0)
EXC_INSTR_ADDR_MISALIGNED = 0
EXC_ILLEGAL_INSTR = 2
EXC_BREAKPOINT = 3
EXC_LOAD_ADDR_MISALIGNED = 4
EXC_STORE_ADDR_MISALIGNED = 6
EXC_ECALL_M = 11

# Interrupt cause (mcause[30:0] with mcause[31] == 1)
INT_M_SOFTWARE = 3
INT_M_TIMER = 7
INT_M_EXTERNAL = 11

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
    """Drive the packed exception_target_addr struct: sub-handles if the simulator exposes
    them, else the flattened 64-bit {second_adder_addr, alu_addr} (verilator's path)."""
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
    """Each machine-mode interrupt line stays masked until both mie and mstatus.MIE are
    set, then raises trap and logs its own mcause/mepc."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # The mie bit position equals the cause number (MSIP=3, MTIP=7, MEIP=11).
    for irq_line, cause in (("timer_interrupt", INT_M_TIMER),
                            ("software_interrupt", INT_M_SOFTWARE),
                            ("external_interrupt", INT_M_EXTERNAL)):
        await reset(dut)

        # A pending interrupt alone does not trap while mie / mstatus.MIE are clear
        getattr(dut, irq_line).value = 1
        await RisingEdge(dut.clk)
        await Timer(2, unit="ns")
        assert dut.trap.value == 0, f"{irq_line}: trap fired with mie and mstatus.MIE clear"

        # Enable this line in mie -- still masked by the global mstatus.MIE
        await csr_write(dut, CSR_MIE, 1 << cause)
        assert dut.trap.value == 0, f"{irq_line}: trap fired with global mstatus.MIE clear"

        # Now set the global enable: the trap must assert combinationally
        dut.current_core_pc.value = 0x0000_1234
        await csr_write(dut, CSR_MSTATUS, 1 << MSTATUS_MIE)
        assert dut.trap.value == 1, f"{irq_line}: trap did not fire when enabled+pending"

        # The trap edge latches mepc and mcause
        await RisingEdge(dut.clk)
        await Timer(2, unit="ns")
        assert await csr_read(dut, CSR_MEPC) == 0x0000_1234, f"{irq_line}: wrong mepc"
        assert await csr_read(dut, CSR_MCAUSE) == (1 << 31) | cause, f"{irq_line}: wrong mcause"


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


@cocotb.test()
async def test_trap_is_one_shot(dut):
    """trap is a single-cycle pulse, so a fault reaches mepc/mcause exactly once: the mask
    holds across a stall, then re-arms on the next unstalled edge with no mret involved."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    dut.stall.value = 0

    # First cycle of an exception -> trap fires.
    dut.current_core_pc.value = 0x0000_2000
    dut.exception.value = 1
    dut.exception_cause.value = EXC_ILLEGAL_INSTR
    await Timer(1, unit="ns")
    assert dut.trap.value == 1, "trap did not fire on the first cycle of an exception"

    # The trap edge latches trap_taken, forcing trap low the next cycle even though the
    # cause is still asserted -> mepc/mcause are captured exactly once.
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert dut.trap.value == 0, "trap did not self-clear -- trap_taken latch missing"

    # A stall must not release the latch (the faulting instruction hasn't retired yet).
    dut.stall.value = 1
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert dut.trap.value == 0, "trap re-fired while stalled with trap_taken set"

    # Unstall and clear the fault (the real core has redirected the PC away by now).
    # The latch self-clears on this unstalled edge, with no mret involved.
    dut.stall.value = 0
    dut.exception.value = 0
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")

    # A fresh exception now traps again: the path re-armed on its own.
    dut.exception.value = 1
    await Timer(1, unit="ns")
    assert dut.trap.value == 1, "trap did not re-arm after the latch self-cleared"


@cocotb.test()
async def test_interrupt_priority(dut):
    """With software, timer and external all pending and enabled, mcause records the
    highest-priority source: external > timer > software."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    dut.software_interrupt.value = 1
    dut.timer_interrupt.value = 1
    dut.external_interrupt.value = 1
    dut.current_core_pc.value = 0x0000_3000

    # Enable all three in mie, then the global mstatus.MIE
    await csr_write(dut, CSR_MIE,
                    (1 << INT_M_SOFTWARE) | (1 << INT_M_TIMER) | (1 << INT_M_EXTERNAL))
    await csr_write(dut, CSR_MSTATUS, 1 << MSTATUS_MIE)
    assert dut.trap.value == 1, "trap did not fire with interrupts pending and enabled"

    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    assert await csr_read(dut, CSR_MCAUSE) == (1 << 31) | INT_M_EXTERNAL, (
        "mcause did not pick the external interrupt (highest priority)"
    )


@cocotb.test()
async def test_mscratch(dut):
    """mscratch is a plain software scratch word: it holds whatever the three CSR ops
    leave in it, and no hardware event (trap entry included) ever touches it. The
    arch-test trap trampoline swaps its save-area pointer through here on every trap,
    so a value that survives a trap is the property that matters."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    assert await csr_read(dut, CSR_MSCRATCH) == 0, "mscratch did not come out of reset at 0"

    # CSRRW overwrites, CSRRS sets bits, CSRRC clears them.
    await csr_write(dut, CSR_MSCRATCH, 0xDEADBEEF)
    assert await csr_read(dut, CSR_MSCRATCH) == 0xDEADBEEF

    await csr_write(dut, CSR_MSCRATCH, 0x0000_0F00, func3=0b010)
    assert await csr_read(dut, CSR_MSCRATCH) == 0xDEADBFEF

    await csr_write(dut, CSR_MSCRATCH, 0x0000_00EF, func3=0b011)
    assert await csr_read(dut, CSR_MSCRATCH) == 0xDEADBF00

    # A write aimed at a different CSR must not land here.
    await csr_write(dut, CSR_MTVEC, 0x8000_0100)
    assert await csr_read(dut, CSR_MSCRATCH) == 0xDEADBF00, "mscratch aliased another CSR"

    # Taking a trap leaves it alone -- unlike mepc/mcause/mtval it has no trap side effect.
    dut.current_core_pc.value = 0x8000_0040
    dut.exception.value = 1
    dut.exception_cause.value = EXC_ILLEGAL_INSTR
    await Timer(1, unit="ns")
    assert dut.trap.value == 1
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    dut.exception.value = 0
    assert await csr_read(dut, CSR_MSCRATCH) == 0xDEADBF00, "trap entry clobbered mscratch"

    # Reset clears it.
    await reset(dut)
    assert await csr_read(dut, CSR_MSCRATCH) == 0


@cocotb.test()
async def test_mtvec_mepc_outputs(dut):
    """The mtvec_out / mepc_out ports mirror their CSRs: mtvec follows a CSR write,
    mepc follows the faulting PC latched on a trap."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # mtvec_out follows a CSR write to mtvec (0x305)
    await csr_write(dut, CSR_MTVEC, 0x8000_0100)
    assert int(dut.mtvec_out.value) == 0x8000_0100, "mtvec_out did not follow the CSR write"

    # mepc_out follows mepc, which latches current_core_pc on a trap
    dut.current_core_pc.value = 0x0000_ABCC
    dut.exception.value = 1
    dut.exception_cause.value = EXC_ILLEGAL_INSTR
    await Timer(1, unit="ns")
    assert dut.trap.value == 1
    await RisingEdge(dut.clk)
    await Timer(2, unit="ns")
    dut.exception.value = 0
    assert int(dut.mepc_out.value) == 0x0000_ABCC, "mepc_out did not follow mepc after a trap"
    # the trap left mtvec untouched
    assert int(dut.mtvec_out.value) == 0x8000_0100


@cocotb.test()
async def test_csr_mapped_decode(dut):
    """csr_mapped is 1 for exactly the addresses the read mux decodes, 0 for everything else."""
    cocotb.start_soon(Clock(dut.clk, 1, unit="ns").start())
    await reset(dut)

    for addr in MAPPED_CSRS:
        dut.address.value = addr
        await Timer(1, unit="ns")
        assert dut.csr_mapped.value == 1, f"CSR {addr:#05x} is implemented but read csr_mapped=0"

    unmapped = [0x000, 0x001, 0x302, 0x306, 0x7C3, 0xC00, 0xF11, 0xF14, 0xFFF]
    for addr in unmapped:
        dut.address.value = addr
        await Timer(1, unit="ns")
        assert dut.csr_mapped.value == 0, f"CSR {addr:#05x} is unimplemented but read csr_mapped=1"
        assert int(dut.read_data.value) == 0, f"unmapped CSR {addr:#05x} must still read 0"

    # csr_mapped must not depend on write_enable: assert a write to an unmapped address and
    # confirm the flag is unchanged (a dependency here would be the loop-closing bug).
    dut.address.value = 0xC00
    dut.write_enable.value = 1
    dut.write_data.value = 0xDEADBEEF
    dut.func3.value = 0b001
    await Timer(1, unit="ns")
    assert dut.csr_mapped.value == 0, "csr_mapped changed with write_enable -- it must depend on address only"
    dut.write_enable.value = 0