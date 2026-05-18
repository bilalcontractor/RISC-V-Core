module memory #(
    parameter WORDS = 64,
    parameter mem_init = ""
) (
    input logic clk,
    input logic [31:0] address,
    input logic [31:0] write_data,
    input logic write_enable, 
    input logic rst_n,

    output logic [31:0] read_data
);

//array of length WORDS, each index 32 bit vector
//essentially a 2D array
logic [31:0] mem [0:WORDS - 1]; 

initial begin 
    $readmemh(mem_init, mem); //load memmory for simulation
end

always_ff @(posedge clk) begin
    //reset logic
    if (!rst_n) begin
        for (int i = 0; i < WORDS; i++) begin
            mem[i] <= 32'b0;
        end
    end
    else if (write_enable) begin
        //ensure the address is aligned to a word boundary
        //if not, we ignore the write
        if (address[1:0] == 2'b00) begin
            //here, address[31:2] is the word index
            mem[address[7:2]] <= write_data;
        end
    end
end

assign read_data = mem[address[7:2]];

endmodule