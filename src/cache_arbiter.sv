import holy_core_pkg::*;

// cache_arbiter : merges the I$ and D$ AXI interfaces onto the single
// external memory bus. Acts as a SLAVE to each cache (it pretends to be
// memory) and as the single MASTER to the outside world. Only one cache
// is connected to m_axi at a time; the instruction cache wins ties.
module cache_arbiter (
    // Master interface facing real memory (arbiter drives requests OUT here)
    axi_if.master m_axi,

    // Slave interfaces facing the caches. To each cache the arbiter looks
    // like its private memory. *_cache_state tells us if that cache wants
    // the bus (anything other than IDLE == needs the bus).
    axi_if.slave s_axi_instruction,
    input cache_state_t i_cache_state,
    axi_if.slave s_axi_data,
    input cache_state_t d_cache_state
);

// The request controller simply muxes the transactions until they are done
// using state info from the caches

always_comb begin
    // STEP 1 - Safe defaults: assume "no traffic" everywhere.
    // Default values set to 0s
    m_axi.awaddr = 0;
    m_axi.awvalid = 0;
    m_axi.wdata = 0;
    m_axi.wlast = 0;
    m_axi.wvalid = 0;
    m_axi.bready = 0;
    m_axi.araddr = 0;
    m_axi.arvalid = 0;
    m_axi.rready = 0;

    // Burst-shape signals (lengths, sizes, ids, strobe). Just zeroed here to
    // avoid latches when both caches are idle; the winning cache drives the
    // real values below, so these defaults are never used for a transaction.
    m_axi.awlen = 0;
    m_axi.awsize = 0;
    m_axi.awburst = 0;
    m_axi.arlen = 0;
    m_axi.arsize = 0;
    m_axi.arburst = 0;
    m_axi.awid = 0;
    m_axi.arid = 0;
    m_axi.wstrb = 0;

    // Tell BOTH caches "no response from memory" by default. We only flip
    // these on for whichever cache actually wins the bus below.
    s_axi_instruction.awready = 0;
    s_axi_instruction.wready = 0;
    s_axi_instruction.bid    = 0;
    s_axi_instruction.bresp  = 0;
    s_axi_instruction.bvalid = 0;
    s_axi_instruction.arready = 0;
    s_axi_instruction.rid    = 0;
    s_axi_instruction.rdata  = 0;
    s_axi_instruction.rresp  = 0;
    s_axi_instruction.rlast  = 0;
    s_axi_instruction.rvalid = 0;

    // ...and tell the data cache the same: no response coming.
    s_axi_data.awready = 0;
    s_axi_data.wready = 0;
    s_axi_data.bid    = 0;
    s_axi_data.bresp  = 0;
    s_axi_data.bvalid = 0;
    s_axi_data.arready = 0;
    s_axi_data.rid    = 0;
    s_axi_data.rdata  = 0;
    s_axi_data.rresp  = 0;
    s_axi_data.rlast  = 0;
    s_axi_data.rvalid = 0;

    // STEP 2 - Pick the winner and splice its wires onto the real bus.
    // Priority: instruction cache first. Checking i_cache_state != IDLE
    // before the data cache is what makes I$ win a tie. Because a cache
    // stays non-IDLE for its whole burst, this connection is held until
    // the transaction finishes (no mid-burst switching).
    //
    // Inside each branch there are two directions of assignment:
    //   m_axi.X = s_axi_*.X  -> forward the cache's REQUEST out to memory
    //   s_axi_*.X = m_axi.X  -> forward memory's REPLY back to the cache
    if (i_cache_state != IDLE) begin
        // --- Instruction cache OWNS the bus ---
        // Write Address Channel (cache -> memory)
        m_axi.awid     = s_axi_instruction.awid;
        m_axi.awaddr   = s_axi_instruction.awaddr;
        m_axi.awlen    = s_axi_instruction.awlen;
        m_axi.awsize   = s_axi_instruction.awsize;
        m_axi.awburst  = s_axi_instruction.awburst;
        m_axi.awvalid  = s_axi_instruction.awvalid;
        s_axi_instruction.awready = m_axi.awready; // ready handshake comes back from memory

        // Write Data Channel (cache -> memory)
        m_axi.wdata    = s_axi_instruction.wdata;
        m_axi.wstrb    = s_axi_instruction.wstrb;
        m_axi.wlast    = s_axi_instruction.wlast;
        m_axi.wvalid   = s_axi_instruction.wvalid;
        s_axi_instruction.wready = m_axi.wready;

        // Write Response Channel (memory -> cache: "write done")
        s_axi_instruction.bid    = m_axi.bid;
        s_axi_instruction.bresp  = m_axi.bresp;
        s_axi_instruction.bvalid = m_axi.bvalid;
        m_axi.bready       = s_axi_instruction.bready;

        // Read Address Channel (cache -> memory)
        m_axi.arid     = s_axi_instruction.arid;
        m_axi.araddr   = s_axi_instruction.araddr;
        m_axi.arlen    = s_axi_instruction.arlen;
        m_axi.arsize   = s_axi_instruction.arsize;
        m_axi.arburst  = s_axi_instruction.arburst;
        m_axi.arvalid  = s_axi_instruction.arvalid;
        s_axi_instruction.arready = m_axi.arready;

        // Read Data Channel (memory -> cache: the fetched data)
        s_axi_instruction.rid    = m_axi.rid;
        s_axi_instruction.rdata  = m_axi.rdata;
        s_axi_instruction.rresp  = m_axi.rresp;
        s_axi_instruction.rlast  = m_axi.rlast;
        s_axi_instruction.rvalid = m_axi.rvalid;
        m_axi.rready       = s_axi_instruction.rready;

    end else if (d_cache_state != IDLE & i_cache_state == IDLE) begin
        // --- Data cache OWNS the bus (only when I$ is idle) ---
        // Same wiring as above, just sourced from / fed to the data cache.
        // Write Address Channel (cache -> memory)
        m_axi.awid     = s_axi_data.awid;
        m_axi.awaddr   = s_axi_data.awaddr;
        m_axi.awlen    = s_axi_data.awlen;
        m_axi.awsize   = s_axi_data.awsize;
        m_axi.awburst  = s_axi_data.awburst;
        m_axi.awvalid  = s_axi_data.awvalid;
        s_axi_data.awready = m_axi.awready;

        // Write Data Channel (cache -> memory)
        m_axi.wdata    = s_axi_data.wdata;
        m_axi.wstrb    = s_axi_data.wstrb;
        m_axi.wlast    = s_axi_data.wlast;
        m_axi.wvalid   = s_axi_data.wvalid;
        s_axi_data.wready = m_axi.wready;

        // Write Response Channel (memory -> cache: "write done")
        s_axi_data.bid    = m_axi.bid;
        s_axi_data.bresp  = m_axi.bresp;
        s_axi_data.bvalid = m_axi.bvalid;
        m_axi.bready      = s_axi_data.bready;

        // Read Address Channel (cache -> memory)
        m_axi.arid     = s_axi_data.arid;
        m_axi.araddr   = s_axi_data.araddr;
        m_axi.arlen    = s_axi_data.arlen;
        m_axi.arsize   = s_axi_data.arsize;
        m_axi.arburst  = s_axi_data.arburst;
        m_axi.arvalid  = s_axi_data.arvalid;
        s_axi_data.arready = m_axi.arready;

        // Read Data Channel (memory -> cache: the fetched data)
        s_axi_data.rid    = m_axi.rid;
        s_axi_data.rdata  = m_axi.rdata;
        s_axi_data.rresp  = m_axi.rresp;
        s_axi_data.rlast  = m_axi.rlast;
        s_axi_data.rvalid = m_axi.rvalid;
        m_axi.rready      = s_axi_data.rready;

    end
    // If neither branch runs, both caches are IDLE and everything stays at
    // the safe 0 defaults from STEP 1 -> the bus is parked, idle.
end

endmodule