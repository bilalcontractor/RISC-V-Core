// Wrapper that groups the two halves of sub-word load/store
// handling into one unit:
//* byte_enable_decoder (STORE path): aligns the register data into the right
// byte lane and produces the byte_enable mask for the memory write.
//* reader              (LOAD path):  takes the raw word back from memory and
// extracts + sign/zero-extends the requested byte/half.
//
// The byte_enable produced by the decoder is consumed by both memory (to mask
// the write) and the reader (to select the load lane). The memory /
// cache itself stays outside: data flows decoder -> memory -> reader.

module load_store_unit import cpu_core_pkg::*; (
    // request info from the datapath
    input  logic [31:0] alu_result_address, // address being accessed (low bits select the lane)
    input  logic [31:0] reg_read,           // store data source (rs2)
    input  logic [2:0]  func3,              // access width + signedness (LB/LH/LW/...)

    // raw word read back from memory / cache
    input  logic [31:0] mem_data,

    // to memory / cache
    output logic [3:0]  byte_enable,        // write mask, also selects the load lane
    output logic [31:0] write_data,         // store data, aligned into its lane

    // to the write-back mux
    output logic [31:0] load_data,          // processed load result
    output logic        load_valid          // low on a misaligned access -> squash write-back
);

    // STORE path: produce the aligned write data + byte_enable mask.
    byte_enable_decoder byte_decoder (
        .alu_result_address (alu_result_address),
        .reg_read           (reg_read),
        .func3              (func3),
        .byte_enable        (byte_enable),
        .data               (write_data)
    );

    // LOAD path: extract + extend the word coming back from memory. Reuses the
    // same byte_enable the decoder just produced to pick the lane.
    reader reader (
        .mem_data        (mem_data),
        .byte_enable     (byte_enable),
        .func3           (func3),
        .write_back_data (load_data),
        .valid           (load_valid)
    );

endmodule
