import cocotb
from cocotb.triggers import Timer
import random


@cocotb.test()
async def add_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0000
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        # We mask expected to not take account of overflows
        expected = (src1 + src2) & 0xFFFFFFFF
        # Await 1 ns for the infos to propagate
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected

@cocotb.test()
async def or_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0011
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        expected = src1 | src2
        # Await 1 ns for the infos to propagate
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected  

@cocotb.test()
async def default_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0111
    src1 = random.randint(0,0xFFFFFFFF)
    src2 = random.randint(0,0xFFFFFFFF)
    dut.src1.value = src1
    dut.src2.value = src2
    expected = 0
    # Await 1 ns for the infos to propagate
    await Timer(1, units="ns")
    assert int(dut.alu_result.value) == expected

@cocotb.test()
async def zero_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0000
    dut.src1.value = 123
    dut.src2.value = -123
    await Timer(1, units="ns")
    print(int(dut.alu_result.value))
    assert int(dut.zero.value) == 1
    assert int(dut.alu_result.value) == 0
    
@cocotb.test()
async def sub_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0001
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        expected = (src1 - src2) & 0xFFFFFFFF

        await Timer(1, units="ns")

        assert str(dut.alu_result.value) == bin(expected)[2:].zfill(32)
        assert int(str(dut.alu_result.value),2) == expected

@cocotb.test()
async def xor_test(dut):
    await Timer(1, units="ns")
    dut.alu_control.value = 0b1000
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        expected = src1 ^ src2
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected

@cocotb.test()
async def and_test(dut):
    # Backs ANDI (and R-type AND): alu_control 0010
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0010
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        expected = src1 & src2
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected

@cocotb.test()
async def slli_test(dut):
    # SLLI: shift left logical by src2[4:0]
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0100
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        shamt = src2 & 0x1F
        expected = (src1 << shamt) & 0xFFFFFFFF
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected

@cocotb.test()
async def srli_test(dut):
    # SRLI: shift right logical by src2[4:0]
    await Timer(1, units="ns")
    dut.alu_control.value = 0b0110
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        shamt = src2 & 0x1F
        expected = src1 >> shamt
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected

@cocotb.test()
async def srai_test(dut):
    # SRAI: arithmetic shift right by src2[4:0] (sign bit is replicated)
    await Timer(1, units="ns")
    dut.alu_control.value = 0b1001
    for _ in range(1000):
        src1 = random.randint(0,0xFFFFFFFF)
        src2 = random.randint(0,0xFFFFFFFF)
        dut.src1.value = src1
        dut.src2.value = src2
        shamt = src2 & 0x1F
        # Interpret src1 as signed, then Python's >> is an arithmetic shift
        signed = src1 - (1 << 32) if (src1 & 0x80000000) else src1
        expected = (signed >> shamt) & 0xFFFFFFFF
        await Timer(1, units="ns")
        assert int(dut.alu_result.value) == expected