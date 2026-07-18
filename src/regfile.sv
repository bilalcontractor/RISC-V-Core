module regfile (
    input logic clk,
    input logic rst_n,
    // Reads
    input logic [4:0] address1,
    input logic [4:0] address2,
    output logic [31:0] read_data1,
    output logic [31:0] read_data2,

    // writes
    input logic write_enable,
    input logic [31:0] write_data,
    input logic [4:0] address3
);

    // 32 bit register. Each addressed with 5 bits
    logic [31:0] registers [0:31];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int i = 0; i < 32; i++) begin
                registers[i] <= 32'b0;
            end
        end
        else if (write_enable && address3 != 0) begin
            registers[address3] <= write_data;
        end
    end

    assign read_data1 = registers[address1];
    assign read_data2 = registers[address2];

endmodule