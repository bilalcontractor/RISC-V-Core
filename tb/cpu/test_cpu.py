# test_cpu.py

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


def binary_to_hex(bin_str):
    # Convert binary string to hexadecimal
    hex_str = hex(int(str(bin_str), 2))[2:]
    hex_str = hex_str.zfill(8)
    return hex_str.upper()

def hex_to_bin(hex_str):
    # Convert hex str to bin
    bin_str = bin(int(str(hex_str), 16))[2:]
    bin_str = bin_str.zfill(32)
    return bin_str.upper()

async def cpu_reset(dut):
    # Init and reset
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)     # Wait for a clock edge after reset
    dut.rst_n.value = 1           # De-assert reset
    await RisingEdge(dut.clk)     # Wait for a clock edge after reset

@cocotb.test()
async def cpu_init_test(dut):
    """Reset the cpu and check for a good imem read"""
    cocotb.start_soon(Clock(dut.clk, 1, units="ns").start())
    await RisingEdge(dut.clk)

    await cpu_reset(dut)
    assert binary_to_hex(dut.pc.value) == "00000000"

    # Load the expected instruction memory as binary
    # Note that this is loaded in sim directly via the verilog code
    # This load is only for expected
    imem = []
    with open("test_imemory.hex", "r") as file:
        for line in file:
            # Ignore comments
            line_content = line.split("//")[0].strip()
            if line_content:
                imem.append(hex_to_bin(line_content))

    # We limit this inital test to the first couple of instructions
    # as we'll later implement branches
    for counter in range(5):
        expected_instruction = imem[counter]
        assert dut.instruction.value == expected_instruction
        await RisingEdge(dut.clk)

@cocotb.test()
async def cpu_insrt_test(dut):
    """Runs a lw datapath test"""
    cocotb.start_soon(Clock(dut.clk, 1, units="ns").start())
    await RisingEdge(dut.clk)

    await cpu_reset(dut)

    print("\n\nTESTING LW\n\n")

    # The first instruction for the test in imem.hex load the data from
    # dmem @ adress 0x00000008 that happens to be 0xDEADBEEF into register x18

    # Wait a clock cycle for the instruction to execute
    await RisingEdge(dut.clk)

    # Check the value of reg x18
    assert binary_to_hex(dut.regfile.registers[18].value) == "DEADBEEF"

    print("\n\nTESTING SW\n\n")
    test_address = int(0xC / 4)
    # The second instruction for the test in imem.hex stores the data from
    # x18 (that happens to be 0xDEADBEEF from the previous LW test) @ adress 0x0000000C

    # First, let's check the inital value
    assert binary_to_hex(dut.data_memory.mem[test_address].value) == "B3B3B3B3"

    # Wait a clock cycle for the instruction to execute
    await RisingEdge(dut.clk)
    # Check the value of mem[0xC]
    assert binary_to_hex(dut.data_memory.mem[test_address].value) == "DEADBEEF"

    # ADD TEST
    # lw x19 0x10(x0) (this memory spot contains 0x00000AAA)
    # add x20 x18 x19

    # Expected result of x18 + x19
    expected_result = (0xDEADBEEF + 0x00000AAA) & 0xFFFFFFFF
    await RisingEdge(dut.clk) # lw x19 0x10(x0)
    assert binary_to_hex(dut.regfile.registers[19].value) == "00000AAA"
    await RisingEdge(dut.clk) # add x20 x18 x19
    assert binary_to_hex(dut.regfile.registers[20].value) == hex(expected_result)[2:].upper()

    # AND TEST
    # and x21 x18 x20 (result shall be 0xDEAD8889)
    expected_result = expected_result & 0xDEADBEEF
    await RisingEdge(dut.clk) # and x21 x18 x20
    assert binary_to_hex(dut.regfile.registers[21].value) == "DEAD8889"
    
    # OR TEST
    # lw x5 0x14(x0) | x5  <= 125F552D
    # lw x6 0x18(x0) | x6  <= 7F4FD46A
    # or x7 x5 x6    | x7  <= 7F5FD56F
    print("\n\nTESTING OR\n\n")
    
    await RisingEdge(dut.clk) # lw x5 0x14(x0) | x5  <= 125F552D
    assert binary_to_hex(dut.regfile.registers[5].value) == "125F552D"
    await RisingEdge(dut.clk) # lw x6 0x18(x0) | x6  <= 7F4FD46A
    assert binary_to_hex(dut.regfile.registers[6].value) == "7F4FD46A"
    await RisingEdge(dut.clk) # or x7 x5 x6    | x7  <= 7F5FD56F
    assert binary_to_hex(dut.regfile.registers[7].value) == "7F5FD56F"