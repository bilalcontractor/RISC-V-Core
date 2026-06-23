import cocotb
from cocotb.triggers import Timer
from cocotb.types import LogicArray

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
    await Timer(1, units="ns")

@cocotb.test()
async def lw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR LW
    await Timer(1, units="ns")
    dut.op.value = 0b0000011 #lw
    await Timer(1, units="ns")
    assert dut.alu_control.value == "0000"
    assert dut.imm_source.value == "000"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    assert dut.pc_source.value == "00"
    
@cocotb.test()
async def sw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR SW
    await Timer(10, units="ns")
    dut.op.value = 0b0100011 #sw
    await Timer(1, units="ns")
    assert dut.alu_control.value == "0000"
    assert dut.imm_source.value == "001"
    assert dut.mem_write.value == "1"
    assert dut.reg_write.value == "0"
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"
    
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
    assert dut.pc_source.value == "00"
    
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
    assert dut.pc_source.value == "00"
    
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
    assert dut.pc_source.value == "00"

    # Test if branching condition is met
    await Timer(3, units="ns")
    dut.alu_zero.value = 0b1
    await Timer(1, units="ns")
    assert dut.pc_source.value == "01"

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
    assert dut.pc_source.value == "01"
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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"

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
    assert dut.pc_source.value == "00"
    
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
    assert dut.pc_source.value == "00"

@cocotb.test()
async def csrrw_control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR CSRRW (register form, func3[2] = 0)
    await Timer(10, units="ns")
    dut.op.value = 0b1110011 # SYSTEM / CSR
    dut.func3.value = 0b001 # csrrw
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
    await Timer(1, units="ns")
    assert dut.csr_write_enable.value == "1"
    assert dut.csr_write_back_source.value == "1" # func3[2]=1 -> immediate
    assert dut.write_back_source.value == "100"

