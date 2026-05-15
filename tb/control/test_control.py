import cocotb
from cocotb.triggers import Timer
import random
from cocotb.binary import BinaryValue

@cocotb.coroutine
async def set_unknown(dut):
    # Set all input to unknown before each test
    await Timer(1, units="ns")
    dut.op.value = BinaryValue("XXXXXXX")
    #
    # Uncomment the following throughout the course when needed
    #
    # dut.func3.value = BinaryValue("XXX")
    # dut.func7.value = BinaryValue("XXXXXXX")
    # dut.alu_zero.value = BinaryValue("X")
    # dut.alu_last_bit.value = BinaryValue("X")
    await Timer(1, units="ns")

@cocotb.test()
async def control_test(dut):
    await set_unknown(dut)
    # TEST CONTROL SIGNALS FOR LW
    await Timer(1, units="ns")
    dut.op.value = 0b0000011 #lw
    await Timer(1, units="ns")
    assert dut.alu_control.value == "000"
    assert dut.imm_source.value == "00"
    assert dut.mem_write.value == "0"
    assert dut.reg_write.value == "1"
    
