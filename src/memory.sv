module memory #(
    parameter WORDS = 1024,
    parameter mem_init = ""
) (
    input logic clk,
    input logic [31:0] address,
    input logic [31:0] write_data,
    input logic [3:0] byte_enable,
    input logic write_enable, 
    input logic rst_n,

    output logic [31:0] read_data
);

    // min number of address bits needed to index every WORD (7 bits for 128 words)
    localparam INDEX_W = $clog2(WORDS);

    // array of length WORDS, each index 32 bit vector
    // essentially a 2D array
    logic [31:0] mem [0:WORDS - 1];

    initial begin 
        $readmemh(mem_init, mem); // load memmory for simulation
    end

    // writeing to memory
    always_ff @(posedge clk) begin
        // reset logic
        if (!rst_n) begin
            for (int i = 0; i < WORDS; i++) begin
                mem[i] <= 32'b0;
            end
        end
        else if (write_enable) begin
            // ensure the address is aligned to a word boundary
            // if not, we ignore the write
            if (address[1:0] == 2'b00) begin
                // use byte-enable to write bytes
                for (int i = 0; i < 4; i++) begin
                    if (byte_enable[i]) begin
                        // address[INDEX_W+1:2] is the specific WORD index (scales with WORDS).
                        // (i*8+:8) --> start at variable location, go 8 bits upward
                        // only write the bytes that the byte mask enable(byte_enable)
                        mem[address[INDEX_W+1:2]][(i*8)+:8] <= write_data[(i*8)+:8];
                    end
                end
            end
        end
    end

    assign read_data = mem[address[INDEX_W+1:2]];

endmodule