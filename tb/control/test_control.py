import cocotb
from cocotb.triggers import Timer
from cocotb.types import LogicArray

# Exception causes (mcause[30:0], mirrors exception_cause_type in cpu_core_pkg).
EXC_ILLEGAL_INSTR = 2
EXC_BREAKPOINT = 3
EXC_LOAD_ADDR_MISALIGNED = 4
EXC_STORE_ADDR_MISALIGNED = 6
EXC_ECALL_M = 11

# Opcodes (mirrors csr_opcode_type / opcode fields in cpu_core_pkg).
OPCODE_I_TYPE_LOAD = 0b0000011
OPCODE_S_TYPE = 0b0100011
OPCODE_CSR = 0b1110011

# SYSTEM instructions, distinguished by instruction[31:20].
ECALL = 0x00000073
EBREAK = 0x00100073
MRET = 0x30200073


def set_exception_target_addr(dut, second_adder_addr, alu_addr):
    """Drive the packed exception_target_addr struct: sub-handles if the simulator exposes
    them, else the flattened 64-bit {second_adder_addr, alu_addr} (verilator's path)."""
    try:
        dut.exception_target_addr.second_adder_addr.value = second_adder_addr
        dut.exception_target_addr.alu_addr.value = alu_addr
    except AttributeError:
        dut.exception_target_addr.value = (second_adder_addr << 32) | alu_addr


async def set_unknown(dut):
    # Set all input to unknown before each test
    await Timer(1, units="ns")
    dut.op.value = LogicArray("XXXXXXX")
    #
    # Uncomment the following throughout the course when needed
    #
    # dut.func3.value = LogicArray("XXX")
    # dut.func7.value = LogicArray("XXXXXXX")
    # dut.alu_zero.value = LogicArray("X")
    # dut.alu_last_bit.value = LogicArray("X")
    # Defined baseline for the CSR-legality inputs so no test reads X. csr_mapped
    # defaults low (unimplemented CSR); tests exercising a legal CSR op raise it.
    dut.instruction.value = 0
    dut.csr_mapped.value = 0
    await Timer(1, units="ns")

@cocotb.test()
async def lw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR LW
    await Timer(1, units="ns")
    dut.op.value = 0b0000011 # lw
    await Timer(1, units="ns")
    assert dut.alu_control.value == "0000"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.pc_source.value == "000"
    
@cocotb.test()
async def sw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SW
    await Timer(10, units="ns")
    dut.op.value = 0b0100011 # sw
    await Timer(1, units="ns")
    assert dut.alu_control.value == "0000"
    assert dut.imm_source.value == "001"
    assert dut.mem_write.value == "1"
    assert dut.reg_write.value == "0"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def add_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR ADD
    await Timer(10, units="ns")
    dut.op.value = 0b0110011 # R-TYPE
    dut.func3.value = 0b000 # add, sub
    dut.func7.value = 0b0000000 # add 
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "0"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"
    
@cocotb.test()
async def and_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR AND
    await Timer(10, units="ns")
    dut.op.value = 0b0110011 # R-TYPE
    # F3 again important
    dut.func3.value = 0b111
    await Timer(1, units="ns")
    assert dut.alu_control.value == "0010"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    # Datapath mux sources
    assert dut.alu_source.value == "0"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"
    
@cocotb.test()
async def or_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR OR
    await Timer(10, units="ns")
    dut.op.value = 0b0110011 
    dut.func3.value = 0b110
    await Timer(1, units="ns")
    # only thing that changes comp to add / and
    assert dut.alu_control.value == "0011"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "0"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"
    
@cocotb.test()
async def beq_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR BEQ
    await Timer(10, units="ns")
    dut.op.value = 0b1100011 # B-TYPE
    dut.func3.value = 0b000 # beq
    dut.alu_zero.value = 0b0
    await Timer(1, units="ns")

    assert dut.imm_source.value == "010"
    assert dut.alu_control.value == "0001"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "0"
    assert dut.alu_source.value == "0"
    assert dut.branch.value == "1"
    assert dut.pc_source.value == "000"

    # Test if branching condition is met
    await Timer(3, units="ns")
    dut.alu_zero.value = 0b1
    await Timer(1, units="ns")
    assert dut.pc_source.value == "001"

@cocotb.test()
async def jal_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR JAL
    await Timer(10, units="ns")
    dut.op.value = 0b1101111 # J-TYPE
    await Timer(1, units="ns")

    assert dut.imm_source.value == "011"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.branch.value == "0"
    assert dut.jump.value == "1"
    assert dut.pc_source.value == "001"
    assert dut.write_back_source.value == "010"
    
@cocotb.test()
async def addi_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR ADDI
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b000 # addi
    await Timer(1, units="ns")

    # Logic block controls
    assert dut.alu_control.value == "0000"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    # Datapath mux sources
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def xori_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR XORI
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b100 # xori
    await Timer(1, units="ns")

    # Logic block controls
    assert dut.alu_control.value == "1000"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    # Datapath mux sources
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def andi_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR ANDI
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b111 # andi
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0010"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def ori_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR ORI
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b110 # ori
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0011"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def slli_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SLLI
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b001 # slli
    dut.func7.value = 0b0000000
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0100"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def srli_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SRLI (func7[5] = 0)
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b101 # srli/srai
    dut.func7.value = 0b0000000 # logical
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0110"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def srai_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SRAI (func7[5] = 1)
    await Timer(10, units="ns")
    dut.op.value = 0b0010011 # I-TYPE
    dut.func3.value = 0b101 # srli/srai
    dut.func7.value = 0b0100000 # arithmetic
    await Timer(1, units="ns")

    assert dut.alu_control.value == "1001"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "1"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"
    
@cocotb.test()
async def sub_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SUB
    await Timer(10, units="ns")
    dut.op.value = 0b0110011 # R-TYPE
    dut.func3.value = 0b000 # add, sub
    dut.func7.value = 0b0100000 # sub
    await Timer(1, units="ns")

    assert dut.alu_control.value == "0001"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.alu_source.value == "0"
    assert dut.write_back_source.value == "000"
    assert dut.pc_source.value == "000"

@cocotb.test()
async def csrrw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR CSRRW (register form, func3[2] = 0)
    await Timer(10, units="ns")
    dut.op.value = 0b1110011 # SYSTEM / CSR
    dut.func3.value = 0b001 # csrrw
    dut.csr_mapped.value = 1 # targeting an implemented CSR
    await Timer(1, units="ns")
    assert dut.imm_source.value == "101"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.write_back_source.value == "100" # old CSR value -> rd
    assert dut.csr_write_enable.value == "1"
    assert dut.csr_write_back_source.value == "0" # func3[2]=0 -> rs1 value

@cocotb.test()
async def csrrwi_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR CSRRWI (immediate form, func3[2] = 1)
    await Timer(10, units="ns")
    dut.op.value = 0b1110011 # SYSTEM / CSR
    dut.func3.value = 0b101 # csrrwi
    dut.csr_mapped.value = 1 # targeting an implemented CSR
    await Timer(1, units="ns")
    assert dut.csr_write_enable.value == "1"
    assert dut.csr_write_back_source.value == "1" # func3[2]=1 -> immediate
    assert dut.write_back_source.value == "100"


# EXCEPTION / TRAP DETECTION
# `exception` defaults to ~i_cache_stall and is ruled out for legal encodings, so every
# test below drives i_cache_stall = 0 and the exception_target_addr struct.

@cocotb.test()
async def illegal_instruction_control_test(dut):
    await set_unknown(dut)
    # TEST ILLEGAL-INSTRUCTION DETECTION: an unknown opcode traps as illegal.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = 0b0000000 # not a valid RV32I opcode
    dut.func3.value = 0b000
    dut.func7.value = 0b0000000
    dut.instruction.value = 0x00000000
    set_exception_target_addr(dut, 0, 0)
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_ILLEGAL_INSTR

@cocotb.test()
async def ecall_control_test(dut):
    await set_unknown(dut)
    # TEST ECALL: legal SYSTEM instruction that deliberately traps as an M-mode ecall.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = OPCODE_CSR
    dut.func3.value = 0b000
    dut.instruction.value = ECALL
    set_exception_target_addr(dut, 0, 0)
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_ECALL_M
    assert dut.mret.value == "0"

@cocotb.test()
async def ebreak_control_test(dut):
    await set_unknown(dut)
    # TEST EBREAK: legal SYSTEM instruction that deliberately traps as a breakpoint.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = OPCODE_CSR
    dut.func3.value = 0b000
    dut.instruction.value = EBREAK
    set_exception_target_addr(dut, 0, 0)
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_BREAKPOINT

@cocotb.test()
async def mret_control_test(dut):
    await set_unknown(dut)
    # TEST MRET: a legal SYSTEM instruction (no exception), asserts mret.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = OPCODE_CSR
    dut.func3.value = 0b000
    dut.instruction.value = MRET
    set_exception_target_addr(dut, 0, 0)
    await Timer(1, units="ns")
    assert dut.mret.value == "1"
    assert dut.exception.value == "0"

@cocotb.test()
async def misaligned_ls_control_test(dut):
    await set_unknown(dut)
    # TEST LOAD/STORE ADDRESS MISALIGNMENT (checked against alu_addr).
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0

    # LW with an aligned effective address: legal, no exception. This doubles as
    # the "a legal instruction rules out the default illegal exception" check.
    dut.op.value = OPCODE_I_TYPE_LOAD
    dut.func3.value = 0b010 # LW (word)
    dut.instruction.value = 0x00000000
    set_exception_target_addr(dut, 0, 0x00000004) # aligned
    await Timer(1, units="ns")
    assert dut.exception.value == "0"

    # Same LW to a misaligned address: load-address-misaligned exception.
    set_exception_target_addr(dut, 0, 0x00000002) # word access, addr % 4 != 0
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_LOAD_ADDR_MISALIGNED

    # SW to a misaligned address: store-address-misaligned exception.
    dut.op.value = OPCODE_S_TYPE
    dut.func3.value = 0b010 # SW (word)
    set_exception_target_addr(dut, 0, 0x00000002)
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_STORE_ADDR_MISALIGNED

@cocotb.test()
async def csr_unmapped_illegal_control_test(dut):
    await set_unknown(dut)
    # TEST UNIMPLEMENTED CSR: accessing an address csrfile does not decode is illegal.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = OPCODE_CSR
    dut.func3.value = 0b010 # csrrs
    dut.instruction.value = 0xC0002D73 # csrrs x26, 0xC00, x0 -> cycle, not implemented
    dut.csr_mapped.value = 0
    set_exception_target_addr(dut, 0, 0)
    await Timer(1, units="ns")
    assert dut.exception.value == "1"
    assert int(dut.exception_cause.value) == EXC_ILLEGAL_INSTR

@cocotb.test()
async def csr_mapped_legal_control_test(dut):
    await set_unknown(dut)
    # TEST IMPLEMENTED CSR: all six CSR func3 encodings are legal when the address decodes.
    await Timer(10, units="ns")
    dut.i_cache_stall.value = 0
    dut.op.value = OPCODE_CSR
    dut.instruction.value = 0x340092F3 # csrrw x5, mscratch, x1
    dut.csr_mapped.value = 1
    set_exception_target_addr(dut, 0, 0)
    for func3 in (0b001, 0b010, 0b011, 0b101, 0b110, 0b111):
        dut.func3.value = func3
        await Timer(1, units="ns")
        assert dut.exception.value == "0", f"mapped CSR op func3={func3:03b} wrongly trapped"
        assert dut.csr_write_enable.value == "1"

