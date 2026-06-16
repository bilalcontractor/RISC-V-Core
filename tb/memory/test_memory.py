import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset(dut):
    await RisingEdge(dut.clk)
    dut.rst_n.value = 0
    dut.write_enable.value = 0
    dut.address.value = 0
    dut.write_data.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Assert all is 0 after reset
    for address in range(dut.WORDS.value):
        dut.address.value = address
        await Timer(1, units="ns")
        # just 32 zeroes, you can also use int()
        assert dut.read_data.value == "00000000000000000000000000000000"


@cocotb.test()
async def memory_data_test(dut):
    # Start a 1 ns clock
    cocotb.start_soon(Clock(dut.clk, 1, unit="ns").start())
    await reset(dut)

    # Reset
    dut.rst_n.value = 0
    dut.write_enable.value = 0
    dut.address.value = 0
    dut.write_data.value = 0  

    await RisingEdge(dut.clk)    
    dut.rst_n.value = 1 
    await RisingEdge(dut.clk)  

    # All is 0 after reset
    for address in range(dut.WORDS.value):
        dut.address.value = address
        await Timer(1, unit="ns")
        assert dut.read_data.value == "00000000000000000000000000000000"
      
    # Test: Write and read back data
    test_data = [
        (0, 0xDEADBEEF),
        (4, 0xCAFEBABE),
        (8, 0x12345678),
        (12, 0xA5A5A5A5)
    ]

    # These are full-WORD writes, so enable all 4 byte lanes.
    # Without this the new byte_enable port defaults to 0 and NOTHING is written.
    dut.byte_enable.value = 0b1111

    for address, data in test_data:
        # Write data to memory
        dut.address.value = address
        dut.write_data.value = data
        dut.write_enable.value = 1
        await RisingEdge(dut.clk)

        # Disable write after one cycle
        dut.write_enable.value = 0
        await RisingEdge(dut.clk)

        # Verify the write by reading back
        dut.address.value = address
        await RisingEdge(dut.clk)
        assert dut.read_data.value == data

    # Test: Write to multiple addresses, then read back
    for i in range(4, 40,4):
        dut.address.value = i
        dut.write_data.value = i + 100
        dut.write_enable.value = 1
        await RisingEdge(dut.clk)

    # Disable write, then read back values to check
    dut.write_enable.value = 0
    for i in range(4, 40,4):
        dut.address.value = i
        await RisingEdge(dut.clk)
        expected_value = i + 100
        assert dut.read_data.value == expected_value


@cocotb.test()
async def memory_byte_enable_test(dut):
    """Sweep every possible byte_enable mask (0b0000 .. 0b1111) and verify the
    memory writes ONLY the enabled byte lanes, leaving the others untouched."""
    cocotb.start_soon(Clock(dut.clk, 1, unit="ns").start())
    await reset(dut)

    test_data = [
        (0, 0xDEADBEEF),
        (4, 0xCAFEBABE),
        (8, 0x12345678),
        (12, 0xA5A5A5A5)
    ]

    # Try all 16 combinations of the 4-bit byte_enable mask.
    for byte_enable in range(16):
        # Start each pass from a clean (all-zero) memory so the "untouched"
        # bytes are known to be 0 -> the expected result is just data & mask.
        await reset(dut)
        dut.byte_enable.value = byte_enable

        # Build the 32-bit bitmask that corresponds to this byte_enable.
        # Each set bit in byte_enable expands to a full 0xFF byte lane.
        # e.g. byte_enable = 0b0101 -> mask = 0x00FF00FF
        mask = 0
        for j in range(4):
            if (byte_enable >> j) & 1:
                mask |= (0xFF << (j * 8))

        for address, data in test_data:
            dut.address.value = address
            dut.write_data.value = data

            # Write for exactly one clock edge, then disable.
            dut.write_enable.value = 1
            await RisingEdge(dut.clk)
            dut.write_enable.value = 0
            await RisingEdge(dut.clk)

            # Read back. read_data is combinational, but wait an edge so the
            # written value has settled before we sample it.
            dut.address.value = address
            await RisingEdge(dut.clk)

            # Only the enabled lanes should hold data; the rest stay 0.
            assert dut.read_data.value == (data & mask), (
                f"byte_enable={byte_enable:04b} addr={address}: "
                f"got {int(dut.read_data.value):#010x}, "
                f"expected {data & mask:#010x}"
            )