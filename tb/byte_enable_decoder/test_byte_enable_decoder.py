# test_byte_enable_decoder.py

import cocotb
from cocotb.triggers import Timer
import random

@cocotb.test()
async def ls_unit_test(dut):
    word = 0x123ABC00

    # SW
    dut.func3.value = 0b010

    for _ in range(100):
        reg_data = random.randint(0, 0xFFFFFFFF)
        dut.reg_read.value = reg_data
        for offset in range(4):
            # drive the low 2 bits of the address with the offset under test
            dut.alu_result_address.value = word | offset
            await Timer(1, unit="ns")  # let the combinational logic settle
            # a word store passes the whole register through unchanged
            assert dut.data.value == reg_data & 0xFFFFFFFF
            if offset == 0b00:
                # only an aligned word store enables all 4 byte lanes
                assert dut.byte_enable.value == 0b1111
            else:
                # misaligned word store is invalid -> no lanes enabled
                assert dut.byte_enable.value == 0b0000

    # SB
    await Timer(10, unit="ns")

    dut.func3.value = 0b000

    for _ in range(100):
        reg_data = random.randint(0, 0xFFFFFFFF)
        dut.reg_read.value = reg_data
        for offset in range(4):
            dut.alu_result_address.value = word | offset
            await Timer(1, units="ns")
            # byte_enable is one-hot, selecting the lane named by the offset;
            # data masks to the low byte then shifts it into that same lane
            if offset == 0b00:
                assert dut.byte_enable.value == 0b0001  # lane 0
                assert dut.data.value == (reg_data & 0x000000FF)
            elif offset == 0b01:
                assert dut.byte_enable.value == 0b0010  # lane 1
                assert dut.data.value == (reg_data & 0x000000FF) << 8
            elif offset == 0b10:
                assert dut.byte_enable.value == 0b0100  # lane 2
                assert dut.data.value == (reg_data & 0x000000FF) << 16
            elif offset == 0b11:
                assert dut.byte_enable.value == 0b1000  # lane 3
                assert dut.data.value == (reg_data & 0x000000FF) << 24
