// cocotbext-axi needs FLAT top-level AXI signals (m_axi_awvalid, ...), but the
// arbiter exposes three SystemVerilog `axi_interface` ports. This wrapper:
//   * instantiates the arbiter as `arbiter` (the name the testbench reaches
//     into for any white-box checks),
//   * splits each axi_interface into flat signals so cocotbext-axi can attach
//       - m_axi      -> an AxiRam   (memory the arbiter masters)
//       - s_axi_instr/s_axi_data -> an AxiMaster each (the caches driving in)
//   * surfaces the two cache_state inputs as plain 3-bit ports the testbench
//     drives to pick who owns the bus.
//
// Direction reminder:
//   m_axi  : arbiter is MASTER  -> arbiter drives aw/w/ar + *ready out, AxiRam
//            drives the responses in.
//   s_axi_*: arbiter is SLAVE   -> the AxiMaster drives aw/w/ar in, arbiter
//            drives awready/rdata/... back out.

module arbiter_axi_wrapper import cpu_core_pkg::*; (
    // clk / rst_n are here only so cocotbext-axi's bus models have a clock and
    // reset to time themselves against; the arbiter itself is combinational.
    input  logic        clk,
    input  logic        rst_n,

    // ---- arbitration inputs : who wants the bus ----
    input  logic [2:0]  i_cache_state,
    input  logic [2:0]  d_cache_state,

    // m_axi : arbiter is MASTER (faces memory / AxiRam)
    // Write address
    output logic [3:0]  m_axi_awid,
    output logic [31:0] m_axi_awaddr,
    output logic [7:0]  m_axi_awlen,
    output logic [2:0]  m_axi_awsize,
    output logic [1:0]  m_axi_awburst,
    output logic        m_axi_awvalid,
    input  logic        m_axi_awready,
    // Write data
    output logic [31:0] m_axi_wdata,
    output logic [3:0]  m_axi_wstrb,
    output logic        m_axi_wlast,
    output logic        m_axi_wvalid,
    input  logic        m_axi_wready,
    // Write response
    input  logic [3:0]  m_axi_bid,
    input  logic [1:0]  m_axi_bresp,
    input  logic        m_axi_bvalid,
    output logic        m_axi_bready,
    // Read address
    output logic [3:0]  m_axi_arid,
    output logic [31:0] m_axi_araddr,
    output logic [7:0]  m_axi_arlen,
    output logic [2:0]  m_axi_arsize,
    output logic [1:0]  m_axi_arburst,
    output logic        m_axi_arvalid,
    input  logic        m_axi_arready,
    // Read data
    input  logic [3:0]  m_axi_rid,
    input  logic [31:0] m_axi_rdata,
    input  logic [1:0]  m_axi_rresp,
    input  logic        m_axi_rlast,
    input  logic        m_axi_rvalid,
    output logic        m_axi_rready,

    // s_axi_instr : arbiter is SLAVE (the I$ AxiMaster drives this in)
    input  logic [3:0]  s_axi_instr_awid,
    input  logic [31:0] s_axi_instr_awaddr,
    input  logic [7:0]  s_axi_instr_awlen,
    input  logic [2:0]  s_axi_instr_awsize,
    input  logic [1:0]  s_axi_instr_awburst,
    input  logic        s_axi_instr_awvalid,
    output logic        s_axi_instr_awready,
    input  logic [31:0] s_axi_instr_wdata,
    input  logic [3:0]  s_axi_instr_wstrb,
    input  logic        s_axi_instr_wlast,
    input  logic        s_axi_instr_wvalid,
    output logic        s_axi_instr_wready,
    output logic [3:0]  s_axi_instr_bid,
    output logic [1:0]  s_axi_instr_bresp,
    output logic        s_axi_instr_bvalid,
    input  logic        s_axi_instr_bready,
    input  logic [3:0]  s_axi_instr_arid,
    input  logic [31:0] s_axi_instr_araddr,
    input  logic [7:0]  s_axi_instr_arlen,
    input  logic [2:0]  s_axi_instr_arsize,
    input  logic [1:0]  s_axi_instr_arburst,
    input  logic        s_axi_instr_arvalid,
    output logic        s_axi_instr_arready,
    output logic [3:0]  s_axi_instr_rid,
    output logic [31:0] s_axi_instr_rdata,
    output logic [1:0]  s_axi_instr_rresp,
    output logic        s_axi_instr_rlast,
    output logic        s_axi_instr_rvalid,
    input  logic        s_axi_instr_rready,

    // s_axi_data : arbiter is SLAVE (the D$ AxiMaster drives this in)
    input  logic [3:0]  s_axi_data_awid,
    input  logic [31:0] s_axi_data_awaddr,
    input  logic [7:0]  s_axi_data_awlen,
    input  logic [2:0]  s_axi_data_awsize,
    input  logic [1:0]  s_axi_data_awburst,
    input  logic        s_axi_data_awvalid,
    output logic        s_axi_data_awready,
    input  logic [31:0] s_axi_data_wdata,
    input  logic [3:0]  s_axi_data_wstrb,
    input  logic        s_axi_data_wlast,
    input  logic        s_axi_data_wvalid,
    output logic        s_axi_data_wready,
    output logic [3:0]  s_axi_data_bid,
    output logic [1:0]  s_axi_data_bresp,
    output logic        s_axi_data_bvalid,
    input  logic        s_axi_data_bready,
    input  logic [3:0]  s_axi_data_arid,
    input  logic [31:0] s_axi_data_araddr,
    input  logic [7:0]  s_axi_data_arlen,
    input  logic [2:0]  s_axi_data_arsize,
    input  logic [1:0]  s_axi_data_arburst,
    input  logic        s_axi_data_arvalid,
    output logic        s_axi_data_arready,
    output logic [3:0]  s_axi_data_rid,
    output logic [31:0] s_axi_data_rdata,
    output logic [1:0]  s_axi_data_rresp,
    output logic        s_axi_data_rlast,
    output logic        s_axi_data_rvalid,
    input  logic        s_axi_data_rready
);

    // The three interfaces the arbiter actually talks to
    axi_interface m_axi_if();
    axi_interface s_instr_if();
    axi_interface s_data_if();

    // m_axi : arbiter MASTER. arbiter -> flat outputs, AxiRam -> flat inputs.
    assign m_axi_awid    = m_axi_if.awid;
    assign m_axi_awaddr  = m_axi_if.awaddr;
    assign m_axi_awlen   = m_axi_if.awlen;
    assign m_axi_awsize  = m_axi_if.awsize;
    assign m_axi_awburst = m_axi_if.awburst;
    assign m_axi_awvalid = m_axi_if.awvalid;
    assign m_axi_wdata   = m_axi_if.wdata;
    assign m_axi_wstrb   = m_axi_if.wstrb;
    assign m_axi_wlast   = m_axi_if.wlast;
    assign m_axi_wvalid  = m_axi_if.wvalid;
    assign m_axi_bready  = m_axi_if.bready;
    assign m_axi_arid    = m_axi_if.arid;
    assign m_axi_araddr  = m_axi_if.araddr;
    assign m_axi_arlen   = m_axi_if.arlen;
    assign m_axi_arsize  = m_axi_if.arsize;
    assign m_axi_arburst = m_axi_if.arburst;
    assign m_axi_arvalid = m_axi_if.arvalid;
    assign m_axi_rready  = m_axi_if.rready;

    assign m_axi_if.awready = m_axi_awready;
    assign m_axi_if.wready  = m_axi_wready;
    assign m_axi_if.bid     = m_axi_bid;
    assign m_axi_if.bresp   = m_axi_bresp;
    assign m_axi_if.bvalid  = m_axi_bvalid;
    assign m_axi_if.arready = m_axi_arready;
    assign m_axi_if.rid     = m_axi_rid;
    assign m_axi_if.rdata   = m_axi_rdata;
    assign m_axi_if.rresp   = m_axi_rresp;
    assign m_axi_if.rlast   = m_axi_rlast;
    assign m_axi_if.rvalid  = m_axi_rvalid;

    // s_axi_instr : arbiter SLAVE. AxiMaster -> flat inputs, arbiter -> outputs.
    assign s_instr_if.awid    = s_axi_instr_awid;
    assign s_instr_if.awaddr  = s_axi_instr_awaddr;
    assign s_instr_if.awlen   = s_axi_instr_awlen;
    assign s_instr_if.awsize  = s_axi_instr_awsize;
    assign s_instr_if.awburst = s_axi_instr_awburst;
    assign s_instr_if.awvalid = s_axi_instr_awvalid;
    assign s_instr_if.wdata   = s_axi_instr_wdata;
    assign s_instr_if.wstrb   = s_axi_instr_wstrb;
    assign s_instr_if.wlast   = s_axi_instr_wlast;
    assign s_instr_if.wvalid  = s_axi_instr_wvalid;
    assign s_instr_if.bready  = s_axi_instr_bready;
    assign s_instr_if.arid    = s_axi_instr_arid;
    assign s_instr_if.araddr  = s_axi_instr_araddr;
    assign s_instr_if.arlen   = s_axi_instr_arlen;
    assign s_instr_if.arsize  = s_axi_instr_arsize;
    assign s_instr_if.arburst = s_axi_instr_arburst;
    assign s_instr_if.arvalid = s_axi_instr_arvalid;
    assign s_instr_if.rready  = s_axi_instr_rready;

    assign s_axi_instr_awready = s_instr_if.awready;
    assign s_axi_instr_wready  = s_instr_if.wready;
    assign s_axi_instr_bid     = s_instr_if.bid;
    assign s_axi_instr_bresp   = s_instr_if.bresp;
    assign s_axi_instr_bvalid  = s_instr_if.bvalid;
    assign s_axi_instr_arready = s_instr_if.arready;
    assign s_axi_instr_rid     = s_instr_if.rid;
    assign s_axi_instr_rdata   = s_instr_if.rdata;
    assign s_axi_instr_rresp   = s_instr_if.rresp;
    assign s_axi_instr_rlast   = s_instr_if.rlast;
    assign s_axi_instr_rvalid  = s_instr_if.rvalid;

    // s_axi_data : arbiter SLAVE. AxiMaster -> flat inputs, arbiter -> outputs.
    assign s_data_if.awid    = s_axi_data_awid;
    assign s_data_if.awaddr  = s_axi_data_awaddr;
    assign s_data_if.awlen   = s_axi_data_awlen;
    assign s_data_if.awsize  = s_axi_data_awsize;
    assign s_data_if.awburst = s_axi_data_awburst;
    assign s_data_if.awvalid = s_axi_data_awvalid;
    assign s_data_if.wdata   = s_axi_data_wdata;
    assign s_data_if.wstrb   = s_axi_data_wstrb;
    assign s_data_if.wlast   = s_axi_data_wlast;
    assign s_data_if.wvalid  = s_axi_data_wvalid;
    assign s_data_if.bready  = s_axi_data_bready;
    assign s_data_if.arid    = s_axi_data_arid;
    assign s_data_if.araddr  = s_axi_data_araddr;
    assign s_data_if.arlen   = s_axi_data_arlen;
    assign s_data_if.arsize  = s_axi_data_arsize;
    assign s_data_if.arburst = s_axi_data_arburst;
    assign s_data_if.arvalid = s_axi_data_arvalid;
    assign s_data_if.rready  = s_axi_data_rready;

    assign s_axi_data_awready = s_data_if.awready;
    assign s_axi_data_wready  = s_data_if.wready;
    assign s_axi_data_bid     = s_data_if.bid;
    assign s_axi_data_bresp   = s_data_if.bresp;
    assign s_axi_data_bvalid  = s_data_if.bvalid;
    assign s_axi_data_arready = s_data_if.arready;
    assign s_axi_data_rid     = s_data_if.rid;
    assign s_axi_data_rdata   = s_data_if.rdata;
    assign s_axi_data_rresp   = s_data_if.rresp;
    assign s_axi_data_rlast   = s_data_if.rlast;
    assign s_axi_data_rvalid  = s_data_if.rvalid;

    cache_arbiter arbiter (
        .m_axi             (m_axi_if.master),
        .s_axi_instruction (s_instr_if.slave),
        .i_cache_state     (cache_state_type'(i_cache_state)),
        .s_axi_data        (s_data_if.slave),
        .d_cache_state     (cache_state_type'(d_cache_state))
    );

endmodule
