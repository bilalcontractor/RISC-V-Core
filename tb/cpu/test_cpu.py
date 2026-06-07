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
    cocotb.start_soon(Clock(dut.clk, 1, units="ns").start())
    await RisingEdge(dut.clk)

    await cpu_reset(dut)
    assert binary_to_hex(dut.pc.value) == "00000000"

    # Load the expected instruction memory as binary
    # This load is only for expected
    imem = []
    with open("test_imemory.hex", "r") as file:
        for line in file:
            # Ignore comments
            line_content = line.split("//")[0].strip()
            if line_content:
                imem.append(hex_to_bin(line_content))

    for counter in range(5):
        expected_instruction = imem[counter]
        assert dut.instruction.value == expected_instruction
        await RisingEdge(dut.clk)

async def test_lw(dut):
    # lw x18 0x8(x0): loads 0xDEADBEEF from dmem @ 0x8 into x18
    print("\n\nTESTING LW\n\n")

    # The first instruction for the test in imem.hex load the data from
    # dmem @ adress 0x00000008 that happens to be 0xDEADBEEF into register x18

    # Wait a clock cycle for the instruction to execute
    await RisingEdge(dut.clk)

    # Check the value of reg x18
    assert binary_to_hex(dut.regfile.registers[18].value) == "DEADBEEF"

async def test_sw(dut):
    # sw x18 0xC(x0): stores 0xDEADBEEF (from x18) @ dmem 0xC
    print("\n\nTESTING SW\n\n")
    test_address = int(0xC / 4)
    # The second instruction for the test in imem.hex stores the data from
    # x18 (that happens to be 0xDEADBEEF from the previous LW test) @ adress 0x0000000C

    # NOTE: no pristine-value check here. cpu_init_test runs first and clocks
    # through the program, executing this same SW, so dmem[0xC] is already
    # DEADBEEF by now ($readmemh only loads once; data_memory never re-inits).

    # Wait a clock cycle for the instruction to execute
    await RisingEdge(dut.clk)
    # Check the value of mem[0xC]
    assert binary_to_hex(dut.data_memory.mem[test_address].value) == "DEADBEEF"

async def test_add(dut):
    # lw x19 0x10(x0) (this memory spot contains 0x00000AAA)
    # add x20 x18 x19

    # Expected result of x18 + x19
    expected_result = (0xDEADBEEF + 0x00000AAA) & 0xFFFFFFFF
    await RisingEdge(dut.clk) # lw x19 0x10(x0)
    assert binary_to_hex(dut.regfile.registers[19].value) == "00000AAA"
    await RisingEdge(dut.clk) # add x20 x18 x19
    assert binary_to_hex(dut.regfile.registers[20].value) == hex(expected_result)[2:].upper()

async def test_and(dut):
    """and x21 x18 x20 (result shall be 0xDEAD8889)"""
    await RisingEdge(dut.clk) # and x21 x18 x20
    assert binary_to_hex(dut.regfile.registers[21].value) == "DEAD8889"

async def test_or(dut):
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

async def test_beq(dut):
    print("\n\nTESTING BEQ\n\n")

    assert binary_to_hex(dut.instruction.value) == "00730663"

    await RisingEdge(dut.clk) # beq x6 x7 0xC NOT TAKEN
    # Check if the current instruction is the one we expected
    assert binary_to_hex(dut.instruction.value) == "00802B03"

    await RisingEdge(dut.clk) # lw x22 0x8(x0)
    assert binary_to_hex(dut.regfile.registers[22].value) == "DEADBEEF"

    await RisingEdge(dut.clk) # beq x18 x22 0x10 TAKEN
    # Check if the current instruction is the one we expected
    assert binary_to_hex(dut.instruction.value) == "00002B03"

    await RisingEdge(dut.clk) # lw x22 0x0(x0)
    assert binary_to_hex(dut.regfile.registers[22].value) == "AEAEAEAE"

    await RisingEdge(dut.clk) # beq x22 x22 -0x8 TAKEN
    # Check if the current instruction is the one we expected
    assert binary_to_hex(dut.instruction.value) == "00000663"

    await RisingEdge(dut.clk) # beq x0 x0 0xC TAKEN
    # Check if the current instruction is the one we expected
    assert binary_to_hex(dut.instruction.value) == "00000013"

async def test_jal(dut):
    #JAL instruction
    print("\n\nTESTING JAL\n\n")

    await RisingEdge(dut.clk) # step over the FINAL NOP @ 0x40 left by the beq test
    await RisingEdge(dut.clk) # jal x1 0xC
    # Check new state & ra (x1) register value
    assert binary_to_hex(dut.instruction.value) == "FFDFF0EF"
    assert binary_to_hex(dut.pc.value) == "00000050"
    assert binary_to_hex(dut.regfile.registers[1].value) == "00000048" # stored old pc + 4

    await RisingEdge(dut.clk) # jal x1 -4
    # Check new state & ra (x1) register value
    assert binary_to_hex(dut.instruction.value) == "00C000EF"
    assert binary_to_hex(dut.pc.value) == "0000004C"
    assert binary_to_hex(dut.regfile.registers[1].value) == "00000054" # stored old pc + 4

    await RisingEdge(dut.clk) # jal x1 0xC
    # Check new state & ra (x1) register value
    assert binary_to_hex(dut.instruction.value) == "00C02383"
    assert binary_to_hex(dut.pc.value) == "00000058"
    assert binary_to_hex(dut.regfile.registers[1].value) == "00000050" # stored old pc + 4

    await RisingEdge(dut.clk) # lw x7 0xC(x0)
    assert binary_to_hex(dut.regfile.registers[7].value) == "DEADBEEF"

async def test_addi(dut):
    # 1AB38D13                      addi x26 x7 0x1AB   | x26 <= DEADC09A
    # F2130C93                      addi x25 x6 0xF21   | x25 <= DEADBE10
    print("\n\nTESTING ADDI\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "1AB38D13"
    assert not binary_to_hex(dut.regfile.registers[26].value) == "DEADC09A"

    await RisingEdge(dut.clk) # addi x26 x7 0x1AB
    assert binary_to_hex(dut.instruction.value) == "F2130C93"
    assert binary_to_hex(dut.regfile.registers[26].value) == "DEADC09A"

    await RisingEdge(dut.clk) # addi x25 x6 0xF21
    assert binary_to_hex(dut.regfile.registers[25].value) == "7F4FD38B"

async def test_auipc(dut):
    # 1F1FA297  //AUIPC TEST START :  auipc x5 0x1F1FA    | x5 <= 1F1FA064
    ##################
    print("\n\nTESTING AUIPC\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "1F1FA297"

    await RisingEdge(dut.clk) # auipc x5 0x1F1FA
    assert binary_to_hex(dut.regfile.registers[5].value) == "1F1FA064"

async def test_lui(dut):
    # LUI TEST
    # 2F2FA2B7  //LUI TEST START :    lui x5 0x2F2FA      | x5 <= 2F2FA000
    ##################
    print("\n\nTESTING LUI\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "2F2FA2B7"

    await RisingEdge(dut.clk) # lui x5 0x2F2FA
    assert binary_to_hex(dut.regfile.registers[5].value) == "2F2FA000"

async def test_slti(dut):
    # FFF9AB93  SLTI TEST START :  slti x23 x19 0xFFF | x23 <= 00000000
    # 001BAB93                     slti x23 x23 0x001 | x23 <= 00000001
    print("\n\nTESTING SLTI\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "FFF9AB93"

    await RisingEdge(dut.clk) # slti x23 x19 0xFFF (x19 positive, imm = -1 -> 0)
    assert binary_to_hex(dut.regfile.registers[23].value) == "00000000"

    await RisingEdge(dut.clk) # slti x23 x23 0x001 (0 < 1 -> 1)
    assert binary_to_hex(dut.regfile.registers[23].value) == "00000001"

async def test_sltiu(dut):
    # FFF9BB13  //SLTIU TEST START :  sltiu x22 x19 0xFFF | x22 <= 00000001
    # 0019BB13  //                    sltiu x22 x19 0x001 | x22 <= 00000000
    print("\n\nTESTING SLTIU\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "FFF9BB13"

    await RisingEdge(dut.clk) # sltiu x22 x19 0xFFF
    assert binary_to_hex(dut.regfile.registers[22].value) == "00000001"

    await RisingEdge(dut.clk) # sltiu x22 x19 0x001
    assert binary_to_hex(dut.regfile.registers[22].value) == "00000000"

async def test_xori(dut):
    # AAA94913  //XORI TEST START :   xori x18 x18 0xAAA  | x18 <= 21524445
    # 00094993  //                    xori x19 x18 0x000  | x19 <= 21524445
    print("\n\nTESTING XORI\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "AAA94913"

    await RisingEdge(dut.clk) # xori x18 x19 0xAAA
    assert binary_to_hex(dut.regfile.registers[18].value) == "21524445"

    await RisingEdge(dut.clk) # xori x19 x18 0x000
    assert (
        binary_to_hex(dut.regfile.registers[19].value) ==
        binary_to_hex(dut.regfile.registers[18].value)
    )

async def test_slli(dut):
    # 00499A13  SLLI TEST START :  slli x20 x19 0x4  | x20 <= 15244450
    print("\n\nTESTING SLLI\n\n")

    assert binary_to_hex(dut.instruction.value) == "00499A13"

    await RisingEdge(dut.clk) # slli x20 x19 0x4
    assert binary_to_hex(dut.regfile.registers[20].value) == "15244450"

async def test_srli(dut):
    # 0089DA93  SRLI TEST START :  srli x21 x19 0x8  | x21 <= 00215244
    print("\n\nTESTING SRLI\n\n")

    assert binary_to_hex(dut.instruction.value) == "0089DA93"

    await RisingEdge(dut.clk) # srli x21 x19 0x8
    assert binary_to_hex(dut.regfile.registers[21].value) == "00215244"

async def test_srai(dut):
    # 4043DB13  SRAI TEST START :  srai x22 x7 0x4   | x22 <= FDEADBEE
    # x7 holds DEADBEEF (MSB set), so the sign bit must be replicated
    print("\n\nTESTING SRAI\n\n")

    assert binary_to_hex(dut.instruction.value) == "4043DB13"

    await RisingEdge(dut.clk) # srai x22 x7 0x4
    assert binary_to_hex(dut.regfile.registers[22].value) == "FDEADBEE"

async def test_ori(dut):
    # F0F9EB93  ORI TEST START :   ori x23 x19 0xF0F | x23 <= FFFFFF4F
    # imm 0xF0F has bit 11 set, so it sign-extends to 0xFFFFFF0F
    print("\n\nTESTING ORI\n\n")

    assert binary_to_hex(dut.instruction.value) == "F0F9EB93"

    await RisingEdge(dut.clk) # ori x23 x19 0xF0F
    assert binary_to_hex(dut.regfile.registers[23].value) == "FFFFFF4F"

async def test_andi(dut):
    # 7A59FC13  ANDI TEST START :  andi x24 x19 0x7A5 | x24 <= 00000405
    # imm 0x7A5 has bit 11 clear, so it zero-extends to 0x000007A5
    print("\n\nTESTING ANDI\n\n")

    assert binary_to_hex(dut.instruction.value) == "7A59FC13"

    await RisingEdge(dut.clk) # andi x24 x19 0x7A5
    assert binary_to_hex(dut.regfile.registers[24].value) == "00000405"

async def test_sub(dut):
    # 412A8933  SUB TEST START :    sub x18 x21 x18  | x18 <= DECF0DFF
    # At this point x21 = 00215244 (from srli) and x18 = 21524445 (from xori),
    # so x21 - x18 borrows -> a negative two's-complement result.
    print("\n\nTESTING SUB\n\n")

    # Check test's init state
    assert binary_to_hex(dut.instruction.value) == "412A8933"

    await RisingEdge(dut.clk) # sub x18 x21 x18
    assert binary_to_hex(dut.regfile.registers[18].value) == "DECF0DFF"

async def test_sll(dut):
    # 00800393  addi x7 x0 0x8     | x7  <= 00000008  (overwrite the DEADBEEF that was in x7)
    # 00791933  sll x18 x18 x7     | x18 <= CF0DFF00  (DECF0DFF << 8, top byte dropped)
    print("\n\nTESTING SLL\n\n")

    # We just executed SUB; the next fetched instruction is the addi.
    assert binary_to_hex(dut.instruction.value) == "00800393"

    await RisingEdge(dut.clk) # addi x7 x0 0x8
    assert binary_to_hex(dut.regfile.registers[7].value) == "00000008"
    assert binary_to_hex(dut.instruction.value) == "00791933"

    await RisingEdge(dut.clk) # sll x18 x18 x7
    assert binary_to_hex(dut.regfile.registers[18].value) == "CF0DFF00"

async def test_slt(dut):
    # 017B28B3  slt x17 x22 x23    | x17 <= 00000001
    # x22 = FDEADBEE (signed -34,956,818), x23 = FFFFFF4F (signed -177).
    # Signed compare: -34,956,818 < -177 -> true -> 1.
    print("\n\nTESTING SLT\n\n")

    assert binary_to_hex(dut.instruction.value) == "017B28B3"

    await RisingEdge(dut.clk) # slt x17 x22 x23
    assert binary_to_hex(dut.regfile.registers[17].value) == "00000001"

async def test_sltu(dut):
    # 017B38B3  sltu x17 x22 x23   | x17 <= 00000001
    # Unsigned: 0xFDEADBEE < 0xFFFFFF4F -> true -> 1.
    print("\n\nTESTING SLTU\n\n")

    assert binary_to_hex(dut.instruction.value) == "017B38B3"

    await RisingEdge(dut.clk) # sltu x17 x22 x23
    assert binary_to_hex(dut.regfile.registers[17].value) == "00000001"

async def test_xor(dut):
    # 013948B3  xor x17 x18 x19    | x17 <= EE5FBB45
    # x18 = CF0DFF00 (after SLL), x19 = 21524445.
    # Byte-wise XOR: CF^21=EE, 0D^52=5F, FF^44=BB, 00^45=45.
    print("\n\nTESTING XOR\n\n")

    assert binary_to_hex(dut.instruction.value) == "013948B3"

    await RisingEdge(dut.clk) # xor x17 x18 x19
    assert binary_to_hex(dut.regfile.registers[17].value) == "EE5FBB45"

async def test_srl(dut):
    # 0079D433  srl x8 x19 x7      | x8  <= 00215244
    # x19 = 21524445 >> 8 (logical, zero fill) = 00215244.
    print("\n\nTESTING SRL\n\n")

    assert binary_to_hex(dut.instruction.value) == "0079D433"

    await RisingEdge(dut.clk) # srl x8 x19 x7
    assert binary_to_hex(dut.regfile.registers[8].value) == "00215244"

async def test_sra(dut):
    # 407B5433  sra x8 x22 x7      | x8  <= FFFDEADB
    # x22 = FDEADBEE (MSB=1), shifted right by 8 (x7) with sign extension.
    print("\n\nTESTING SRA\n\n")

    assert binary_to_hex(dut.instruction.value) == "407B5433"

    await RisingEdge(dut.clk) # sra x8 x22 x7
    assert binary_to_hex(dut.regfile.registers[8].value) == "FFFDEADB"

async def test_blt(dut):
    # 00744663  BLT TEST START :  blt x8 x7 0xC   | x8 < x7 (signed) -> TAKEN
    #   x8 = FFFDEADB (signed -136485), x7 = 00000008 (+8): -136485 < 8 is true,
    #   so the branch is taken: `addi x28 x0 0x7AD` is SKIPPED and we
    #   land directly on `addi x28 x0 0x111`.
    # 0083C663                    blt x7 x8 0xC   | x7 < x8 (signed) -> NOT TAKEN
    #   8 < -136485 is false, so we fall through to `addi x29 x0 0x222`.
    print("\n\nTESTING BLT\n\n")

    # We just executed SRA; the blt is the next fetched instruction.
    assert binary_to_hex(dut.instruction.value) == "00744663"

    await RisingEdge(dut.clk) # blt x8 x7 0xC TAKEN
    # PC jumped over the poison addi straight to the landing addi
    assert binary_to_hex(dut.instruction.value) == "11100E13"

    await RisingEdge(dut.clk) # addi x28 x0 0x111 (landing)
    # 0x111 (not 0x7AD) proves the poison instruction was skipped
    assert binary_to_hex(dut.regfile.registers[28].value) == "00000111"
    # Next fetched instruction is the second blt
    assert binary_to_hex(dut.instruction.value) == "0083C663"

    await RisingEdge(dut.clk) # blt x7 x8 0xC NOT TAKEN
    # No redirect: the very next sequential instruction is fetched
    assert binary_to_hex(dut.instruction.value) == "22200E93"

    await RisingEdge(dut.clk) # addi x29 x0 0x222 (fall-through)
    assert binary_to_hex(dut.regfile.registers[29].value) == "00000222"

async def test_jalr(dut):
    # 0E000293  JALR TEST START : addi x5 x0 0xE0    | x5  <= 000000E0  (jump base address)
    # 008280E7                    jalr x1 0x8(x5)    | pc  <= x5 + 0x8 = 0xE8, x1 <= old pc + 4 = 0xD8
    #   The offset (0x8) must be ADDED to rs1 in the ALU, so we skip the
    #   poison instrs at 0xD8 (addi x6 0x111) and 0xE0 (addi x7 0x7AD) and
    #   land directly on the addi at 0xE8.
    # 22200E13                    addi x28 x0 0x222  | x28 <= 00000222  (proves we landed)
    print("\n\nTESTING JALR\n\n")

    # We just executed the BLT fall-through addi; the addi that loads the
    # jalr base address is the next fetched instruction (@ 0xD0).
    assert binary_to_hex(dut.instruction.value) == "0E000293"

    await RisingEdge(dut.clk) # addi x5 x0 0xE0
    assert binary_to_hex(dut.regfile.registers[5].value) == "000000E0"
    # The jalr itself is now fetched (@ 0xD4)
    assert binary_to_hex(dut.instruction.value) == "008280E7"

    await RisingEdge(dut.clk) # jalr x1 0x8(x5)
    # PC jumped to rs1 + offset = 0xE0 + 0x8 = 0xE8, skipping both poisons
    assert binary_to_hex(dut.pc.value) == "000000E8"
    # Link register x1 holds the old pc + 4 = 0xD4 + 4 = 0xD8
    assert binary_to_hex(dut.regfile.registers[1].value) == "000000D8"
    # The landing instruction is now fetched
    assert binary_to_hex(dut.instruction.value) == "22200E13"

    await RisingEdge(dut.clk) # addi x28 x0 0x222 (landing)
    # 0x222 (not the poison 0x111 / 0x7AD) proves rs1+offset jump worked
    assert binary_to_hex(dut.regfile.registers[28].value) == "00000222"
    
async def test_sb(dut):
    # 0EE00413  //SB TEST START :     addi x8 x0 0xEE     | x8 <= 000000EE
    # 008020A3  //                    sw x8 0x1(x0)       | NO WRITE ! (mis-aligned !)
    # 00800323  //                    sb x8 0x6(x0)       | mem @ 0x4 <= 00EE0000
    #   The addi loads x8 with a known clean value (low byte EE) so this test
    #   does not depend on whatever earlier tests left in x8.
    print("\n\nTESTING SB\n\n")

    # The addi that sets up x8 is the freshly fetched instruction
    assert binary_to_hex(dut.instruction.value) == "0EE00413"

    await RisingEdge(dut.clk) # addi x8 x0 0xEE
    assert binary_to_hex(dut.regfile.registers[8].value) == "000000EE"
    # the sw is now fetched
    assert binary_to_hex(dut.instruction.value) == "008020A3"

    await RisingEdge(dut.clk) # sw x8 0x1(x0)
    # address is 1 because 0x6 is word @ address 4 and the test bench gets data by word
    # misaligned word store (offset 0b01) -> byte_enable 0000 -> no write
    assert binary_to_hex(dut.data_memory.mem[1].value) == "00000000"

    await RisingEdge(dut.clk) # sb x8 0x6(x0)
    # low byte of x8 (EE) lands in byte lane 2 (address 0x6 -> word 1, offset 2)
    assert binary_to_hex(dut.data_memory.mem[1].value) == "00EE0000"

@cocotb.test()
async def cpu_insrt_test(dut):
    """Runs the full instruction datapath test"""
    cocotb.start_soon(Clock(dut.clk, 1, units="ns").start())
    await RisingEdge(dut.clk)

    await cpu_reset(dut)

    await test_lw(dut)
    await test_sw(dut)
    await test_add(dut)
    await test_and(dut)
    await test_or(dut)
    await test_beq(dut)
    await test_jal(dut)
    await test_addi(dut)
    await test_auipc(dut)
    await test_lui(dut)
    await test_slti(dut)
    await test_sltiu(dut)
    await test_xori(dut)
    await test_slli(dut)
    await test_srli(dut)
    await test_srai(dut)
    await test_ori(dut)
    await test_andi(dut)
    await test_sub(dut)
    await test_sll(dut)
    await test_slt(dut)
    await test_sltu(dut)
    await test_xor(dut)
    await test_srl(dut)
    await test_sra(dut)
    await test_blt(dut)
    await test_jalr(dut)
    await test_sb(dut)
