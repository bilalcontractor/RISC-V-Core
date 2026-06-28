interface axi_lite_interface #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32
);

    // Global AXI Signals
    logic aclk;
    logic aresetn;

    // Write Address Channel
    logic [ADDR_WIDTH-1:0] awaddr;
    logic awvalid;
    logic awready;

    // Write Data Channel
    logic [DATA_WIDTH-1:0] wdata;
    logic [(DATA_WIDTH/8)-1:0] wstrb;  // Write strobe
    logic wvalid;
    logic wready;

    // Write Response Channel
    logic [1:0] bresp;  // Write response
    logic bvalid;
    logic bready;

    // Read Address Channel
    logic [ADDR_WIDTH-1:0] araddr;
    logic arvalid;
    logic arready;

    // Read Data Channel
    logic [DATA_WIDTH-1:0] rdata;
    logic [1:0] rresp;  // Read response
    logic rvalid;
    logic rready;

    // Define modport for master
    modport master (
        input  aclk,
        input  aresetn,

        // Write Address Channel
        output awaddr,
        output awvalid,
        input  awready,

        // Write Data Channel
        output wdata,
        output wstrb,
        output wvalid,
        input  wready,

        // Write Response Channel
        input  bresp,
        input  bvalid,
        output bready,

        // Read Address Channel
        output araddr,
        output arvalid,
        input  arready,

        // Read Data Channel
        input  rdata,
        input  rresp,
        input  rvalid,
        output rready
    );

    // Define modport for slave
    modport slave (
        input  aclk,
        input  aresetn,

        // Write Address Channel
        input  awaddr,
        input  awvalid,
        output awready,

        // Write Data Channel
        input  wdata,
        input  wstrb,
        input  wvalid,
        output wready,

        // Write Response Channel
        output bresp,
        output bvalid,
        input  bready,

        // Read Address Channel
        input  araddr,
        input  arvalid,
        output arready,

        // Read Data Channel
        output rdata,
        output rresp,
        output rvalid,
        input  rready
    );

endinterface
