# The CPU no longer owns its memory: its two caches (instruction + data) share a
# single external AXI bus through the arbiter. So instead of $readmemh-ing a
# memory module, we attach a cocotbext-axi AxiRam to the flat m_axi bus exposed
# by test_harness.sv and pre-load it with the program and its data.
#
# Testbench MEMORY MAP (unified, one AxiRam):
#   0x0000 .. 0x0FFF : instructions  (program image)
#   0x1000 .. 0x1FFF : data          (base address kept in x3 / gp)
# The program's very first instruction is `lui x3 0x1`, loading 0x00001000 into
# x3 so every load/store can address the data region as `off(x3)`.
#
# STALLING: a cache miss freezes the pipeline. global_stall (an instruction
# fetch miss OR a load/store data miss) holds the PC and squashes the register
# write until the miss is served. Our cache is direct-mapped with 8-word lines,
# so a fresh fetch stalls at every new line. The tick()/wait_fetch() helpers hide
# all of that: every test still reads as "one tick == one retired instruction".
#
# This file only covers the instruction-level regression (cpu_insrt_test and its
# per-instruction sub-tests). Whole-program flows (RISCOF signature dump, the
# spike-style commit logger, and the UART free-run) live in test_program.py -
# they share the harness helpers in sim_common.py but exercise a full compiled
# binary rather than this file's small hand-assembled instruction stream.


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotbext.axi import AxiBus, AxiRam, AxiLiteBus, AxiLiteRam

from sim_common import (
    CPU_PERIOD, AXI_PERIOD, MEM_BYTES, SENDING_WRITE_REQUEST,
    binary_to_hex, read_cache,
    settle, wait_fetch, tick, init_memory, cpu_reset,
)


async def test_data_base(dut):
    # lui x3 0x1 : x3 <= 0x00001000, the base address of the data region.
    print("\n\nSAVING DATA BASE ADDR\n\n")
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000000"
    assert binary_to_hex(dut.cpu_system.instruction.value) == "000011B7"
    await tick(dut)  # lui x3 0x1
    assert binary_to_hex(dut.cpu_system.regfile.registers[3].value) == "00001000"


async def test_lw(dut):
    # lw x18 0x8(x3) : loads 0xDEADBEEF from data @ 0x1008 into x18.
    print("\n\nTESTING LW\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0081A903"
    await tick(dut)  # lw x18 0x8(x3)
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "DEADBEEF"


async def test_sw(dut):
    # sw x18 0xC(x3) : stores 0xDEADBEEF (x18) to data @ 0x100C.
    # We check the data cache, not the AxiRam: the write hits the already-loaded
    # line and stays there (write-back only happens on eviction).
    print("\n\nTESTING SW\n\n")
    test_index = int(0xC / 4)  # word 3 of the loaded data line
    assert read_cache(dut.cpu_system.data_cache.cache_data, test_index) == 0xF2F2F2F2
    await tick(dut)  # sw x18 0xC(x3)
    assert read_cache(dut.cpu_system.data_cache.cache_data, test_index) == 0xDEADBEEF


async def test_add(dut):
    # lw x19 0x10(x3) ; add x20 x18 x19
    print("\n\nTESTING ADD\n\n")
    expected_result = (0xDEADBEEF + 0x00000AAA) & 0xFFFFFFFF
    await tick(dut)  # lw x19 0x10(x3)
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "00000AAA"
    await tick(dut)  # add x20 x18 x19
    assert dut.cpu_system.regfile.registers[20].value == expected_result


async def test_and(dut):
    # and x21 x18 x20 -> 0xDEAD8889
    print("\n\nTESTING AND\n\n")
    await tick(dut)  # and x21 x18 x20
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "DEAD8889"


async def test_or(dut):
    # lw x5 0x14(x3) ; lw x6 0x18(x3) ; or x7 x5 x6
    print("\n\nTESTING OR\n\n")
    await tick(dut)  # lw x5 0x14(x3) | x5 <= 125F552D
    assert binary_to_hex(dut.cpu_system.regfile.registers[5].value) == "125F552D"
    await tick(dut)  # lw x6 0x18(x3) | x6 <= 7F4FD46A
    assert binary_to_hex(dut.cpu_system.regfile.registers[6].value) == "7F4FD46A"
    await tick(dut)  # or x7 x5 x6    | x7 <= 7F5FD56F
    assert binary_to_hex(dut.cpu_system.regfile.registers[7].value) == "7F5FD56F"


async def test_beq(dut):
    print("\n\nTESTING BEQ\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00730663"

    await tick(dut)  # beq x6 x7 0xC : NOT TAKEN
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0081AB03"

    await tick(dut)  # lw x22 0x8(x3)
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "DEADBEEF"

    await tick(dut)  # beq x18 x22 0x10 : TAKEN (forward)
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0001AB03"

    await tick(dut)  # lw x22 0x0(x3)
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "AEAEAEAE"

    await tick(dut)  # beq x22 x22 -0x8 : TAKEN (backward)
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00000663"

    await tick(dut)  # beq x0 x0 0xC : TAKEN
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00000013"

    await tick(dut)  # FINAL NOP, step onto the JAL test


async def test_jal(dut):
    print("\n\nTESTING JAL\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00C000EF"
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000048"

    await tick(dut)  # jal x1 0xC (forward)
    assert binary_to_hex(dut.cpu_system.instruction.value) == "FFDFF0EF"
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000054"
    assert binary_to_hex(dut.cpu_system.regfile.registers[1].value) == "0000004C"  # old pc + 4

    await tick(dut)  # jal x1 -4 (backward)
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00C000EF"
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000050"
    assert binary_to_hex(dut.cpu_system.regfile.registers[1].value) == "00000058"  # old pc + 4

    await tick(dut)  # jal x1 0xC (forward)
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00C1A383"
    assert binary_to_hex(dut.cpu_system.pc.value) == "0000005C"
    assert binary_to_hex(dut.cpu_system.regfile.registers[1].value) == "00000054"  # old pc + 4

    await tick(dut)  # lw x7 0xC(x3)
    assert binary_to_hex(dut.cpu_system.regfile.registers[7].value) == "DEADBEEF"


async def test_addi(dut):
    # addi x26 x7 0x1AB ; addi x25 x6 0xF21
    print("\n\nTESTING ADDI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "1AB38D13"
    assert not binary_to_hex(dut.cpu_system.regfile.registers[26].value) == "DEADC09A"

    await tick(dut)  # addi x26 x7 0x1AB
    assert binary_to_hex(dut.cpu_system.instruction.value) == "F2130C93"
    assert binary_to_hex(dut.cpu_system.regfile.registers[26].value) == "DEADC09A"

    await tick(dut)  # addi x25 x6 0xF21
    assert binary_to_hex(dut.cpu_system.regfile.registers[25].value) == "7F4FD38B"


async def test_auipc(dut):
    # auipc x5 0x1F1FA @ PC 0x68 -> x5 <= 0x68 + 0x1F1FA000 = 0x1F1FA068
    print("\n\nTESTING AUIPC\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "1F1FA297"
    await tick(dut)  # auipc x5 0x1F1FA
    assert binary_to_hex(dut.cpu_system.regfile.registers[5].value) == "1F1FA068"


async def test_lui(dut):
    # lui x5 0x2F2FA -> x5 <= 0x2F2FA000
    print("\n\nTESTING LUI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "2F2FA2B7"
    await tick(dut)  # lui x5 0x2F2FA
    assert binary_to_hex(dut.cpu_system.regfile.registers[5].value) == "2F2FA000"


async def test_slti(dut):
    # slti x23 x19 0xFFF (-1) -> 0 ; slti x23 x23 0x001 -> 1
    print("\n\nTESTING SLTI\n\n")
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "00000AAA"
    assert binary_to_hex(dut.cpu_system.instruction.value) == "FFF9AB93"

    await tick(dut)  # slti x23 x19 0xFFF
    assert binary_to_hex(dut.cpu_system.regfile.registers[23].value) == "00000000"

    await tick(dut)  # slti x23 x23 0x001
    assert binary_to_hex(dut.cpu_system.regfile.registers[23].value) == "00000001"


async def test_sltiu(dut):
    # sltiu x22 x19 0xFFF -> 1 ; sltiu x22 x19 0x001 -> 0
    print("\n\nTESTING SLTIU\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "FFF9BB13"

    await tick(dut)  # sltiu x22 x19 0xFFF
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "00000001"

    await tick(dut)  # sltiu x22 x19 0x001
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "00000000"


async def test_xori(dut):
    # xori x18 x19 0xAAA (sign-extended) ; xori x19 x18 0x000 (copy)
    print("\n\nTESTING XORI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "AAA94913"

    await tick(dut)  # xori x18 x19 0xAAA
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "21524445"

    await tick(dut)  # xori x19 x18 0x000
    assert (binary_to_hex(dut.cpu_system.regfile.registers[19].value)
            == binary_to_hex(dut.cpu_system.regfile.registers[18].value))


async def test_ori(dut):
    # ori x20 x19 0xAAA (sign-extended) ; ori x21 x20 0x000 (copy)
    print("\n\nTESTING ORI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "AAA9EA13"

    await tick(dut)  # ori x20 x19 0xAAA
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "FFFFFEEF"

    await tick(dut)  # ori x21 x20 0x000
    assert (binary_to_hex(dut.cpu_system.regfile.registers[21].value)
            == binary_to_hex(dut.cpu_system.regfile.registers[20].value))


async def test_andi(dut):
    # andi x18 x20 0x7FF ; andi x19 x21 0xFFF ; andi x20 x21 0x000
    print("\n\nTESTING ANDI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "7FFA7913"

    await tick(dut)  # andi x18 x20 0x7FF
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "000006EF"

    await tick(dut)  # andi x19 x21 0xFFF
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "FFFFFEEF"

    await tick(dut)  # andi x20 x21 0x000
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "00000000"


async def test_slli(dut):
    # slli x19 x19 0x4 -> FFFFEEF0. The following NOP stands in for the course's
    # illegal-funct7 probe (no illegal-op detection here yet), so x19 is unchanged.
    print("\n\nTESTING SLLI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00499993"

    await tick(dut)  # slli x19 x19 0x4
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "FFFFEEF0"

    await tick(dut)  # nop (invalid-op probe omitted)
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "FFFFEEF0"


async def test_srli(dut):
    # srli x20 x19 0x4 -> 0FFFFEEF, then a NOP (invalid-op probe omitted).
    print("\n\nTESTING SRLI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0049DA13"

    await tick(dut)  # srli x20 x19 0x4
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "0FFFFEEF"

    await tick(dut)  # nop (invalid-op probe omitted)
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "0FFFFEEF"


async def test_srai(dut):
    # srai x21 x21 0x4 -> FFFFFFEE (sign replicated), then a NOP.
    print("\n\nTESTING SRAI\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "404ADA93"

    await tick(dut)  # srai x21 x21 0x4
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "FFFFFFEE"

    await tick(dut)  # nop (invalid-op probe omitted)
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "FFFFFFEE"


async def test_sub(dut):
    # sub x18 x21 x18 -> FFFFF8FF (x21=FFFFFFEE - x18=000006EF)
    print("\n\nTESTING SUB\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "412A8933"
    await tick(dut)  # sub x18 x21 x18
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "FFFFF8FF"


async def test_sll(dut):
    # addi x7 x0 0x8 ; sll x18 x18 x7 -> FFF8FF00
    print("\n\nTESTING SLL\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00800393"
    await tick(dut)  # addi x7 x0 0x8
    assert binary_to_hex(dut.cpu_system.regfile.registers[7].value) == "00000008"

    await tick(dut)  # sll x18 x18 x7
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "FFF8FF00"


async def test_slt(dut):
    # slt x17 x22 x23 -> 1
    print("\n\nTESTING SLT\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "013928B3"
    await tick(dut)  # slt x17 x22 x23
    assert binary_to_hex(dut.cpu_system.regfile.registers[17].value) == "00000001"


async def test_sltu(dut):
    # sltu x17 x22 x23 -> 1
    print("\n\nTESTING SLTU\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "013938B3"
    await tick(dut)  # sltu x17 x22 x23
    assert binary_to_hex(dut.cpu_system.regfile.registers[17].value) == "00000001"


async def test_xor(dut):
    # xor x17 x18 x19 -> 000711F0 (FFF8FF00 ^ FFFFEEF0)
    print("\n\nTESTING XOR\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "013948B3"
    await tick(dut)  # xor x17 x18 x19
    assert binary_to_hex(dut.cpu_system.regfile.registers[17].value) == "000711F0"


async def test_srl(dut):
    # srl x8 x19 x7 -> 00FFFFEE (FFFFEEF0 >> 8, logical)
    print("\n\nTESTING SRL\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0079D433"
    await tick(dut)  # srl x8 x19 x7
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "00FFFFEE"


async def test_sra(dut):
    # sra x8 x19 x7 -> FFFFFFEE (FFFFEEF0 >> 8, arithmetic)
    print("\n\nTESTING SRA\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "4079D433"
    await tick(dut)  # sra x8 x19 x7
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_blt(dut):
    # blt x17 x8 (pos < neg) NOT taken ; blt x8 x17 (neg < pos) TAKEN
    print("\n\nTESTING BLT\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0088C463"
    assert binary_to_hex(dut.cpu_system.regfile.registers[17].value) == "000711F0"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"

    await tick(dut)  # blt x17 x8 0x8 : NOT taken
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01144463"

    await tick(dut)  # blt x8 x17 0x8 : TAKEN (skips the poison addi)
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_bne(dut):
    # bne x8 x8 NOT taken ; bne x8 x17 TAKEN
    print("\n\nTESTING BNE\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00841463"

    await tick(dut)  # bne x8 x8 0x8 : NOT taken
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01141463"

    await tick(dut)  # bne x8 x17 0x8 : TAKEN
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_bge(dut):
    # bge x8 x17 (neg >= pos) NOT taken ; bge x8 x8 (equal) TAKEN
    print("\n\nTESTING BGE\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01145463"

    await tick(dut)  # bge x8 x17 0x8 : NOT taken
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00845463"

    await tick(dut)  # bge x8 x8 0x8 : TAKEN
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_bltu(dut):
    # bltu x8 x17 (big < small unsigned) NOT taken ; bltu x17 x8 TAKEN
    print("\n\nTESTING BLTU\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01146463"

    await tick(dut)  # bltu x8 x17 0x8 : NOT taken
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0088E463"

    await tick(dut)  # bltu x17 x8 0x8 : TAKEN
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_bgeu(dut):
    # bgeu x17 x8 (small >= big unsigned) NOT taken ; bgeu x8 x17 TAKEN
    print("\n\nTESTING BGEU\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "0088F463"

    await tick(dut)  # bgeu x17 x8 0x8 : NOT taken
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01147463"

    await tick(dut)  # bgeu x8 x17 0x8 : TAKEN
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"


async def test_jalr(dut):
    # auipc x7 0x0 ; addi x7 x7 0x14 ; jalr x1 -4(x7)
    # jalr target = x7 - 4 = 0x120, link x1 = pc + 4 = 0x11C.
    print("\n\nTESTING JALR\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00000397"
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000110"

    await tick(dut)  # auipc x7 0x0   -> x7 = 0x110
    await tick(dut)  # addi x7 x7 0x14 -> x7 = 0x124
    assert binary_to_hex(dut.cpu_system.regfile.registers[7].value) == "00000124"

    await tick(dut)  # jalr x1 -4(x7)
    assert binary_to_hex(dut.cpu_system.regfile.registers[1].value) == "0000011C"  # link = pc + 4
    assert not binary_to_hex(dut.cpu_system.instruction.value) == "00C00413"        # skipped poison addi
    assert binary_to_hex(dut.cpu_system.regfile.registers[8].value) == "FFFFFFEE"    # x8 untouched
    assert binary_to_hex(dut.cpu_system.pc.value) == "00000120"                      # x7 + offset


async def test_sb(dut):
    # sw x8 0x1(x0) : misaligned -> no write ; sb x8 0x6(x3) : byte EE into lane 2
    print("\n\nTESTING SB\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "008020A3"

    await tick(dut)  # sw x8 0x1(x0) : misaligned word store, byte_enable 0 -> no write
    # word index 1 = data @ 0x1004, still its reset value
    assert read_cache(dut.cpu_system.data_cache.cache_data, 1) == 0x00000000
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00818323"

    await tick(dut)  # sb x8 0x6(x3) : low byte EE -> byte lane 2 of word @ 0x1004
    assert read_cache(dut.cpu_system.data_cache.cache_data, 1) == 0x00EE0000


async def test_sh(dut):
    # sh x8 1(x0), sh x8 3(x0) : misaligned -> no write ; sh x8 6(x3) : half FFEE into lanes 2,3
    print("\n\nTESTING SH\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "008010A3"

    await tick(dut)  # sh x8 1(x0) : misaligned -> no write
    assert read_cache(dut.cpu_system.data_cache.cache_data, 1) == 0x00EE0000

    await tick(dut)  # sh x8 3(x0) : misaligned -> no write
    assert read_cache(dut.cpu_system.data_cache.cache_data, 1) == 0x00EE0000

    await tick(dut)  # sh x8 6(x3) : upper half of word @ 0x1004 <= FFEE
    assert read_cache(dut.cpu_system.data_cache.cache_data, 1) == 0xFFEE0000


async def test_loads(dut):
    # Partial loads off x7 = x3 + 0x10 = 0x1010, reaching back into the data line.
    # dmem @ 0x100C = DEADBEEF (from the SW test), @ 0x1008 = DEADBEEF.
    print("\n\nTESTING PARTIAL LOADS (lb/lbu/lh/lhu)\n\n")
    assert binary_to_hex(dut.cpu_system.instruction.value) == "01018393"

    await tick(dut)  # addi x7 x3 0x10 -> x7 = 0x1010
    assert binary_to_hex(dut.cpu_system.regfile.registers[7].value) == "00001010"

    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "FFF8FF00"
    await tick(dut)  # lw x18 -1(x7) : misaligned word -> reg write squashed
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "FFF8FF00"

    await tick(dut)  # lb x18 -1(x7) : byte @ 0x100F = DE, sign-extended
    assert binary_to_hex(dut.cpu_system.regfile.registers[18].value) == "FFFFFFDE"

    await tick(dut)  # lbu x19 -3(x7) : byte @ 0x100D = BE, zero-extended
    assert binary_to_hex(dut.cpu_system.regfile.registers[19].value) == "000000BE"

    await tick(dut)  # lh x20 -3(x7) : misaligned half -> reg write squashed
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "0FFFFEEF"

    await tick(dut)  # lh x20 -6(x7) : half @ 0x100A = DEAD, sign-extended
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "FFFFDEAD"

    await tick(dut)  # lhu x21 -3(x7) : misaligned half -> reg write squashed
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "FFFFFFEE"

    await tick(dut)  # lhu x21 -6(x7) : half @ 0x100A = DEAD, zero-extended
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "0000DEAD"


async def test_csr(dut):
    # CSR FLUSH_CACHE test:
    #   addi x20 x0 0x1     | x20 <= 00000001
    #   csrrw x21 0x7C0 x20 | x21 <= 00000000  (old CSR value)
    print("\n\nTESTING CSR (FLUSH_CACHE)\n\n")

    # Check test init's state: x21 still holds 0000DEAD from the loads test, addi up next.
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "0000DEAD"
    assert binary_to_hex(dut.cpu_system.instruction.value) == "00100A13"

    await tick(dut)  # addi x20 x0 0x1
    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "00000001"
    assert binary_to_hex(dut.cpu_system.instruction.value) == "7C0A1AF3"

    # csrrw x21 0x7C0 x20 : commit it by hand (tick() would hide the flush stall).
    await RisingEdge(dut.clk)  # csrrw x21 0x7C0 x20
    await settle()
    # value in the CSR was 0...
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "00000000"

    # The CSR write set flush_cache, so the pipeline now stalls while the dirty data
    # cache performs its CSR-ordered write-back (IDLE -> SENDING_WRITE_REQUEST).
    assert dut.cpu_system.global_stall.value == 0b1
    assert binary_to_hex(dut.cpu_system.csr_file.flush_cache.value) == "00000001"

    await RisingEdge(dut.clk)
    await settle()
    assert dut.cpu_system.data_cache.state.value == SENDING_WRITE_REQUEST

    # Wait for the cache to finish writing the line back.
    while dut.cpu_system.global_stall.value == 0b1:
        await RisingEdge(dut.clk)
        await settle()

    # At the end of the stall, the flush CSR should be back to 0.
    assert dut.cpu_system.global_stall.value == 0b0
    assert binary_to_hex(dut.cpu_system.csr_file.flush_cache.value) == "00000000"


async def test_mmio(dut, axi_lite_ram):
    print("\n\nTESTING MMIO (UNCACHABLE RANGE)\n\n")

    assert binary_to_hex(dut.cpu_system.instruction.value) == "00000A13"
    await tick(dut)  # addi x20 x0 0x0

    await tick(dut)  # lui x20 0x2
    await tick(dut)  # addi x21 x20 0x200

    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "00002000"
    assert binary_to_hex(dut.cpu_system.regfile.registers[21].value) == "00002200"

    await tick(dut)  # csrrw x0 0x7C1 x20
    await tick(dut)  # csrrw x0 0x7C2 x21

    assert binary_to_hex(dut.cpu_system.csr_file.non_cachable_base.value) == "00002000"
    assert binary_to_hex(dut.cpu_system.csr_file.non_cachable_limit.value) == "00002200"

    await tick(dut)  # addi x20 x20 0x4
    await tick(dut)  # lui x22 0xABCD1
    await tick(dut)  # addi x22 x22 0x111

    assert binary_to_hex(dut.cpu_system.regfile.registers[20].value) == "00002004"
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "ABCD1111"

    # make sure data is initialy 0 where we'll test
    axi_lite_ram.write(0x0000_2004, int(0x0000_0000).to_bytes(4, 'little'))
    axi_lite_ram.write(0x0000_2008, int(0x0000_0000).to_bytes(4, 'little'))

    # sw x22 0(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert axi_lite_ram.read(0x0000_2004, 4) == (0xABCD1111).to_bytes(4, "little")

    # lw x22 4(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "00000000"

    # lw x22 0(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert binary_to_hex(dut.cpu_system.regfile.registers[22].value) == "ABCD1111"

    # PARTIAL MMIO TESTS
    # addi x23 x0 0xEE
    await settle()
    await tick(dut)
    assert binary_to_hex(dut.cpu_system.regfile.registers[23].value) == "000000EE"

    # sb x23 0(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert axi_lite_ram.read(0x0000_2004, 4) == (0xABCD11EE).to_bytes(4, "little")

    # addi x24 x0 0x123
    await settle()
    await tick(dut)
    assert binary_to_hex(dut.cpu_system.regfile.registers[24].value) == "00000123"

    # sh x24 2(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert axi_lite_ram.read(0x0000_2004, 4) == (0x012311EE).to_bytes(4, "little")

    # lw x25 0(x20)
    await settle()
    assert dut.cpu_system.data_cache.is_non_cachable.value == 0b1
    await tick(dut)
    assert binary_to_hex(dut.cpu_system.regfile.registers[25].value) == "012311EE"


@cocotb.test()
async def cpu_insrt_test(dut):
    """Walk the full instruction datapath against an AXI-attached unified memory."""
    cocotb.start_soon(Clock(dut.clk, CPU_PERIOD, units="ns").start())
    cocotb.start_soon(Clock(dut.clk, AXI_PERIOD, units="ns").start())

    # An AxiRam plays main memory on the CPU's flat m_axi bus. rst_n is active-low,
    # hence reset_active_level=False.
    axi_ram = AxiRam(AxiBus.from_prefix(dut, "m_axi"), dut.clk, dut.rst_n,
                     size=MEM_BYTES, reset_active_level=False)

    axi_lite_ram = AxiLiteRam(AxiLiteBus.from_prefix(dut, "m_axi_lite"), dut.clk, dut.rst_n,
                              size=MEM_BYTES, reset_active_level=False)

    await cpu_reset(dut)

    # Program the unified memory: code at 0x0000, data at 0x1000.
    await init_memory(axi_ram, "./test_imemory.hex", 0x0000)
    await init_memory(axi_ram, "./test_dmemory.hex", 0x1000)

    # Land on the first fetched instruction (the initial fetch misses and refills).
    await wait_fetch(dut)

    await test_data_base(dut)
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
    await test_ori(dut)
    await test_andi(dut)
    await test_slli(dut)
    await test_srli(dut)
    await test_srai(dut)
    await test_sub(dut)
    await test_sll(dut)
    await test_slt(dut)
    await test_sltu(dut)
    await test_xor(dut)
    await test_srl(dut)
    await test_sra(dut)
    await test_blt(dut)
    await test_bne(dut)
    await test_bge(dut)
    await test_bltu(dut)
    await test_bgeu(dut)
    await test_jalr(dut)
    await test_sb(dut)
    await test_sh(dut)
    await test_loads(dut)
    await test_csr(dut)
    await test_mmio(dut, axi_lite_ram)
