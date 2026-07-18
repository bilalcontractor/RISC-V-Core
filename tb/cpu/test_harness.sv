// cocotbext-axi's AxiRam needs FLAT top-level AXI signals (m_axi_awvalid, ...),
// but the CPU exposes its single external memory bus as a SystemVerilog
// `axi_interface` port (m_axi). This harness:
//* instantiates the CPU as `cpu_system` (the name the testbench reaches into
// for white-box checks: cpu_system.pc, cpu_system.instruction,
// cpu_system.regfile.registers[...], cpu_system.data_cache.cache_data, ...),
//* splits the m_axi interface into flat master signals so a single AxiRam can
// play the unified main memory that both caches share through the arbiter.
//
// Direction reminder: the CPU is the AXI MASTER here. It drives the aw/w/ar
// request channels and the *ready signals out; the AxiRam drives the
// awready/wready/b*/rdata/... responses back in.
//
// Only one clock is exposed (clk): the CPU ties its caches' AXI clock to the
// CPU clock internally, so the whole design - and the AxiRam attached to it -
// lives in a single clock domain. rst_n is active-low (AxiRam: reset_active_level=False).
module test_harness import cpu_core_pkg::*; (
    input  logic        clk,
    input  logic        rst_n,

    //---- Flattened AXI master signals (for cocotbext-axi AxiRam) ----
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

    //---- Flattened AXI-Lite master signals (MMIO bypass) ----
    // Write address
    output logic [31:0] m_axi_lite_awaddr,
    output logic        m_axi_lite_awvalid,
    input  logic        m_axi_lite_awready,
    // Write data
    output logic [31:0] m_axi_lite_wdata,
    output logic [3:0]  m_axi_lite_wstrb,
    output logic        m_axi_lite_wvalid,
    input  logic        m_axi_lite_wready,
    // Write response
    input  logic [1:0]  m_axi_lite_bresp,
    input  logic        m_axi_lite_bvalid,
    output logic        m_axi_lite_bready,
    // Read address
    output logic [31:0] m_axi_lite_araddr,
    output logic        m_axi_lite_arvalid,
    input  logic        m_axi_lite_arready,
    // Read data
    input  logic [31:0] m_axi_lite_rdata,
    input  logic [1:0]  m_axi_lite_rresp,
    input  logic        m_axi_lite_rvalid,
    output logic        m_axi_lite_rready
);

    // The interfaces the CPU actually masters.
    axi_interface      m_axi();
    axi_lite_interface m_axi_lite();

    //---- master -> slave : driven by the CPU, exported to the top ----
    assign m_axi_awid    = m_axi.awid;
    assign m_axi_awaddr  = m_axi.awaddr;
    assign m_axi_awlen   = m_axi.awlen;
    assign m_axi_awsize  = m_axi.awsize;
    assign m_axi_awburst = m_axi.awburst;
    assign m_axi_awvalid = m_axi.awvalid;
    assign m_axi_wdata   = m_axi.wdata;
    assign m_axi_wstrb   = m_axi.wstrb;
    assign m_axi_wlast   = m_axi.wlast;
    assign m_axi_wvalid  = m_axi.wvalid;
    assign m_axi_bready  = m_axi.bready;
    assign m_axi_arid    = m_axi.arid;
    assign m_axi_araddr  = m_axi.araddr;
    assign m_axi_arlen   = m_axi.arlen;
    assign m_axi_arsize  = m_axi.arsize;
    assign m_axi_arburst = m_axi.arburst;
    assign m_axi_arvalid = m_axi.arvalid;
    assign m_axi_rready  = m_axi.rready;

    //---- slave -> master : driven by the AxiRam, fed into the CPU ----
    assign m_axi.awready = m_axi_awready;
    assign m_axi.wready  = m_axi_wready;
    assign m_axi.bid     = m_axi_bid;
    assign m_axi.bresp   = m_axi_bresp;
    assign m_axi.bvalid  = m_axi_bvalid;
    assign m_axi.arready = m_axi_arready;
    assign m_axi.rid     = m_axi_rid;
    assign m_axi.rdata   = m_axi_rdata;
    assign m_axi.rresp   = m_axi_rresp;
    assign m_axi.rlast   = m_axi_rlast;
    assign m_axi.rvalid  = m_axi_rvalid;

    //---- AXI-Lite master -> slave : driven by the CPU, exported to the top ----
    assign m_axi_lite_awaddr  = m_axi_lite.awaddr;
    assign m_axi_lite_awvalid = m_axi_lite.awvalid;
    assign m_axi_lite_wdata   = m_axi_lite.wdata;
    assign m_axi_lite_wstrb   = m_axi_lite.wstrb;
    assign m_axi_lite_wvalid  = m_axi_lite.wvalid;
    assign m_axi_lite_bready  = m_axi_lite.bready;
    assign m_axi_lite_araddr  = m_axi_lite.araddr;
    assign m_axi_lite_arvalid = m_axi_lite.arvalid;
    assign m_axi_lite_rready  = m_axi_lite.rready;

    //---- AXI-Lite slave -> master : driven by the MMIO model, fed into the CPU ----
    assign m_axi_lite.awready = m_axi_lite_awready;
    assign m_axi_lite.wready  = m_axi_lite_wready;
    assign m_axi_lite.bresp   = m_axi_lite_bresp;
    assign m_axi_lite.bvalid  = m_axi_lite_bvalid;
    assign m_axi_lite.arready = m_axi_lite_arready;
    assign m_axi_lite.rdata   = m_axi_lite_rdata;
    assign m_axi_lite.rresp   = m_axi_lite_rresp;
    assign m_axi_lite.rvalid  = m_axi_lite_rvalid;

    cpu cpu_system (
        .clk       (clk),
        .rst_n     (rst_n),
        .m_axi     (m_axi.master),
        .m_axi_lite (m_axi_lite.master)
    );

    // The UART now lives entirely in the testbench (uart_bridge in test_cpu.py):
    // a Python coroutine snoops these AXI-Lite signals to transmit TX bytes and
    // injects RX bytes into the AxiLiteRam, modelling a full bidirectional UART
    // without any simulation-only RTL here.

endmodule
