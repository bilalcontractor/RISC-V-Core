module alu (
    //In
    input logic [3:0] alu_control,
    input logic [31:0] src1,
    input logic [31:0] src2,
    //Out
    output logic [31:0] alu_result,
    output logic zero,
    output logic alu_last
);

assign alu_last = alu_result[0]; //last bit of result
assign zero = (alu_result == 32'b0);

always_comb begin 
    case(alu_control)
        4'b0000: alu_result = src1 + src2; //ADD
        4'b0010: alu_result = src1 & src2; //AND
        4'b0011: alu_result = src1 | src2; //OR
        4'b0001: alu_result = src1 + (~src2 + 1'b1); // SUB. Use two's complement(rs1 - rs2)
        4'b0101: alu_result = {31'b0, $signed(src1) < $signed(src2)}; //src1 < src2
        4'b0111: alu_result = {31'b0, src1 < src2}; //src1 < src2(UNSIGNED)
        4'b1000: alu_result = src1 ^ src2; //XOR

        //Shifts by lowest 5 bits --> src2[4:0]
        4'b0100: alu_result = src1 << src2[4:0]; //SLLI --> shift left logical immediate
        4'b1001: alu_result = $signed(src1) >>> src2[4:0]; //SRAI --> shift right arithmetic immediate
        4'b0110: alu_result = src1 >> src2[4:0]; //SRLI --> shift right logical immediate

        default: alu_result = 32'b0;
    endcase
end

endmodule