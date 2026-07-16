# Shared cocotb harness helpers used by both the instruction-level regression
# (test_cpu.py) and the whole-program flows (test_program.py: RISCOF signature
# dump, spike-style commit logger, UART free-run).

from cocotb.triggers import RisingEdge, ReadOnly, Timer

CPU_PERIOD = 10        # ns
AXI_PERIOD = 10
SETTLE = 1             # ns, let combinational signals settle before sampling
MEM_BYTES = 2 ** 14    # 16 KiB unified memory (code @ 0x0000, data @ 0x1000)

# cache_state_type encoding (order must match cpu_core_pkg::cache_state_type)
IDLE = 0
SENDING_WRITE_REQUEST = 1
SENDING_WRITE_DATA = 2
WAITING_WRITE_RECIEVE = 3
SENDING_READ_REQUEST = 4
RECIEVING_READ_DATA = 5


def binary_to_hex(bin_str):
    # Convert a binary string (a signal's .value) to an 8-char hex string.
    hex_str = hex(int(str(bin_str), 2))[2:]
    return hex_str.zfill(8).upper()


def hex_to_bin(hex_str):
    # Convert a hex string to a 32-bit binary string.
    bin_str = bin(int(str(hex_str), 16))[2:]
    return bin_str.zfill(32).upper()


def read_cache(cache_data, index):
    # Pull word `index` out of the data cache's packed cache_data vector.
    # cache_data is packed [NUM_SETS-1:0][WORDS_PER_LINE-1:0][31:0], so the word
    # at flat index N (= address[8:2]) lives at bits [N*32 +: 32]. We read the
    # whole vector as an int and shift, which sidesteps any slice-direction issues.
    full = cache_data.value.to_unsigned()
    return (full >> (index * 32)) & 0xFFFFFFFF


async def settle():
    # Let combinational outputs (instruction, read_data, stall...) propagate.
    await Timer(SETTLE, units="ns")


async def wait_fetch(dut):
    # Block until the instruction cache has the word at the current PC ready.
    await settle()
    while dut.cpu_system.i_cache_stall.value == 1:
        await RisingEdge(dut.clk)
        await settle()


async def tick(dut):
    # Retire exactly one instruction, then realign on the next valid fetch.
    # global_stall freezes the PC / squashes the reg write, so the instruction
    # only commits on an unstalled edge: wait the stall out, take the committing
    # edge, then wait for the next fetch to be valid so `instruction` is safe to
    # inspect by the caller.
    await settle()
    while dut.cpu_system.global_stall.value == 1:
        await RisingEdge(dut.clk)
        await settle()
    await RisingEdge(dut.clk)   # commits the current instruction
    await wait_fetch(dut)


async def count_cycles(dut, counter):
    # Tally every clock edge for as long as this runs. Counting here rather than
    # in the caller's loop is what makes stalls visible: tick() waits global_stall
    # out, so a loop over tick() sees retired instructions only, and the gap
    # between that and this counter IS the cache-miss cost.
    while True:
        await RisingEdge(dut.clk)
        counter[0] += 1


async def init_memory(axi_ram, hexfile, base_addr):
    # Load a hex image (one 32-bit word per line, optional "// comment") into the
    # AxiRam, little-endian, one word per 4 bytes
    offset = 0
    with open(hexfile, "r") as file:
        for line in file:
            text = line.split("//")[0].strip()
            if not text:
                continue
            word = int(text, 16).to_bytes(4, "little")
            axi_ram.write(base_addr + offset, word)
            offset += 4


async def cpu_reset(dut):
    # Drive active-low reset for a couple of cycles, then release.
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await settle()


async def uart_bridge(dut, tx_capture, *, tx_addr=0x0000_2010):
    # Pure-Python UART TX snooper (no DPI-C, no synthesizable RTL).
    #
    # The AxiLiteRam stays the real AXI-Lite slave that ACKs every beat and backs
    # the STATUS read (0x2014), which is zero-initialised => bit3 (TX busy) = 0 =
    # "TX ready", so the program's polling loop proceeds. This coroutine only
    # OBSERVES the write channel: whenever it sees a completed byte write to the TX
    # register (0x2010) it appends the byte to tx_capture, reconstructing the
    # character stream the CPU is "printing".
    #
    # Assumption: the CPU presents the write ADDRESS on/before the DATA beat (true
    # for the holy_core AXI-Lite MMIO path), so at the data handshake we use the
    # just-seen address, else the one latched at the earlier AW handshake.
    latched_awaddr = 0

    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()

        aw_hs = dut.m_axi_lite_awvalid.value == 1 and dut.m_axi_lite_awready.value == 1
        w_hs  = dut.m_axi_lite_wvalid.value  == 1 and dut.m_axi_lite_wready.value  == 1

        if aw_hs:
            latched_awaddr = int(dut.m_axi_lite_awaddr.value)

        if w_hs:
            eff_addr = int(dut.m_axi_lite_awaddr.value) if aw_hs else latched_awaddr
            wstrb = int(dut.m_axi_lite_wstrb.value)
            if eff_addr == tx_addr and (wstrb & 0x1):
                tx_capture.append(int(dut.m_axi_lite_wdata.value) & 0xFF)
