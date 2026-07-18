// Test wrapper for the data_cache (AXI full + AXI-Lite).
//
// cocotbext-axi's AxiRam needs FLAT top-level AXI signals (axi_awvalid, ...),
// but the cache exposes SystemVerilog `axi_interface` / `axi_lite_interface`
// ports. This wrapper:
//* instantiates the cache as `cache_system` (the name the testbench reaches
// into for white-box checks),
//* renames the CPU ports to cpu_* so the testbench reads clearly,
//* splits both the axi_interface and axi_lite_interface into flat master
// signals for cocotbext-axi,
//* surfaces the cache_state / set_ptr debug taps as top-level ports so the
// testbench does not have to reach into internals for them.
module cache_axi_wrapper import cpu_core_pkg::*; #(
    parameter CACHE_SIZE = 128,
    parameter NUM_SETS   = 16
)(
    input  logic        clk,
    input  logic        rst_n,
    input  logic        aclk,

    //---- CPU side ----
    input  logic [31:0] cpu_address,
    input  logic [31:0] cpu_write_data,
    input  logic        cpu_read_enable,
    input  logic        cpu_write_enable,
    input  logic [3:0]  cpu_byte_enable,
    input  logic        cpu_csr_flush_order,
    input  logic [31:0] cpu_non_cachable_base,
    input  logic [31:0] cpu_non_cachable_limit,
    output logic [31:0] cpu_read_data,
    output logic        cpu_cache_stall,

    //---- debug taps ----
    output logic [3:0]  cpu_cache_state,
    output logic [6:0]  cpu_set_ptr,

    //---- Flattened AXI master signals (for cocotbext-axi AxiRam) ----
    // Write address
    output logic [3:0]  axi_awid,
    output logic [31:0] axi_awaddr,
    output logic [7:0]  axi_awlen,
    output logic [2:0]  axi_awsize,
    output logic [1:0]  axi_awburst,
    output logic        axi_awvalid,
    input  logic        axi_awready,
    // Write data
    output logic [31:0] axi_wdata,
    output logic [3:0]  axi_wstrb,
    output logic        axi_wlast,
    output logic        axi_wvalid,
    input  logic        axi_wready,
    // Write response
    input  logic [3:0]  axi_bid,
    input  logic [1:0]  axi_bresp,
    input  logic        axi_bvalid,
    output logic        axi_bready,
    // Read address
    output logic [3:0]  axi_arid,
    output logic [31:0] axi_araddr,
    output logic [7:0]  axi_arlen,
    output logic [2:0]  axi_arsize,
    output logic [1:0]  axi_arburst,
    output logic        axi_arvalid,
    input  logic        axi_arready,
    // Read data
    input  logic [3:0]  axi_rid,
    input  logic [31:0] axi_rdata,
    input  logic [1:0]  axi_rresp,
    input  logic        axi_rlast,
    input  logic        axi_rvalid,
    output logic        axi_rready,

    //---- Flattened AXI-Lite master signals (MMIO bypass) ----
    // Write address
    output logic [31:0] axi_lite_awaddr,
    output logic        axi_lite_awvalid,
    input  logic        axi_lite_awready,
    // Write data
    output logic [31:0] axi_lite_wdata,
    output logic [3:0]  axi_lite_wstrb,
    output logic        axi_lite_wvalid,
    input  logic        axi_lite_wready,
    // Write response
    input  logic [1:0]  axi_lite_bresp,
    input  logic        axi_lite_bvalid,
    output logic        axi_lite_bready,
    // Read address
    output logic [31:0] axi_lite_araddr,
    output logic        axi_lite_arvalid,
    input  logic        axi_lite_arready,
    // Read data
    input  logic [31:0] axi_lite_rdata,
    input  logic [1:0]  axi_lite_rresp,
    input  logic        axi_lite_rvalid,
    output logic        axi_lite_rready
);

    // The interfaces the cache actually talks to
    axi_interface      axi_if();
    axi_lite_interface axi_lite_if();

    //====================
    // AXI FULL
    //====================

    //---- master -> slave : driven by the cache, exported to the top ----
    assign axi_awid    = axi_if.awid;
    assign axi_awaddr  = axi_if.awaddr;
    assign axi_awlen   = axi_if.awlen;
    assign axi_awsize  = axi_if.awsize;
    assign axi_awburst = axi_if.awburst;
    assign axi_awvalid = axi_if.awvalid;
    assign axi_wdata   = axi_if.wdata;
    assign axi_wstrb   = axi_if.wstrb;
    assign axi_wlast   = axi_if.wlast;
    assign axi_wvalid  = axi_if.wvalid;
    assign axi_bready  = axi_if.bready;
    assign axi_arid    = axi_if.arid;
    assign axi_araddr  = axi_if.araddr;
    assign axi_arlen   = axi_if.arlen;
    assign axi_arsize  = axi_if.arsize;
    assign axi_arburst = axi_if.arburst;
    assign axi_arvalid = axi_if.arvalid;
    assign axi_rready  = axi_if.rready;

    //---- slave -> master : driven by the AxiRam, fed into the cache ----
    assign axi_if.awready = axi_awready;
    assign axi_if.wready  = axi_wready;
    assign axi_if.bid     = axi_bid;
    assign axi_if.bresp   = axi_bresp;
    assign axi_if.bvalid  = axi_bvalid;
    assign axi_if.arready  = axi_arready;
    assign axi_if.rid     = axi_rid;
    assign axi_if.rdata   = axi_rdata;
    assign axi_if.rresp   = axi_rresp;
    assign axi_if.rlast   = axi_rlast;
    assign axi_if.rvalid  = axi_rvalid;

    //====================
    // AXI LITE
    //====================

    //---- master -> slave : driven by the cache, exported to the top ----
    assign axi_lite_awaddr  = axi_lite_if.awaddr;
    assign axi_lite_awvalid = axi_lite_if.awvalid;
    assign axi_lite_wdata   = axi_lite_if.wdata;
    assign axi_lite_wstrb   = axi_lite_if.wstrb;
    assign axi_lite_wvalid  = axi_lite_if.wvalid;
    assign axi_lite_bready  = axi_lite_if.bready;
    assign axi_lite_araddr  = axi_lite_if.araddr;
    assign axi_lite_arvalid = axi_lite_if.arvalid;
    assign axi_lite_rready  = axi_lite_if.rready;

    //---- slave -> master : driven by the AxiRam, fed into the cache ----
    assign axi_lite_if.awready = axi_lite_awready;
    assign axi_lite_if.wready  = axi_lite_wready;
    assign axi_lite_if.bresp   = axi_lite_bresp;
    assign axi_lite_if.bvalid  = axi_lite_bvalid;
    assign axi_lite_if.arready  = axi_lite_arready;
    assign axi_lite_if.rdata   = axi_lite_rdata;
    assign axi_lite_if.rresp   = axi_lite_rresp;
    assign axi_lite_if.rvalid  = axi_lite_rvalid;

    // debug taps
    cache_state_type cache_state_w;
    assign cpu_cache_state = cache_state_w;

    data_cache #(
        .CACHE_SIZE (CACHE_SIZE),
        .NUM_SETS   (NUM_SETS)
    ) cache_system (
        .clk                (clk),
        .rst_n              (rst_n),
        .aclk               (aclk),
        .address            (cpu_address),
        .write_data         (cpu_write_data),
        .read_enable        (cpu_read_enable),
        .write_enable       (cpu_write_enable),
        .byte_enable        (cpu_byte_enable),
        .csr_flush_order    (cpu_csr_flush_order),
        .non_cachable_base  (cpu_non_cachable_base),
        .non_cachable_limit (cpu_non_cachable_limit),
        .read_data          (cpu_read_data),
        .cache_stall        (cpu_cache_stall),
        .axi                (axi_if.master),
        .axi_lite           (axi_lite_if.master),
        .cache_state        (cache_state_w),
        .set_ptr_out        (cpu_set_ptr),
        .next_set_ptr_out   ()
    );

endmodule
