module alu (
    //In
    input logic [2:0] alu_control,
    input logic [31:0] src1,
    input logic [31:0] src2,
    //Out
    output logic [31:0] alu_result,
    output logic zero
);

always_comb begin 
    case(alu_control)
        3'b000: alu_result = src1 + src2; //ADD
        3'b010: alu_result = src1 & src2; //AND
        3'b011: alu_result = src1 | src2; //OR
        3'b001: alu_result = src1 + (~src2 + 1'b1); // SUB. Use two's complement(rs1 - rs2)
        3'b101: alu_result = {31'b0, $signed(src1) < $signed(src2)}; //src1 < src2 
        3'b111: alu_result = {31'b0, src1 < src2}; //src1 < src2(UNSIGNED)
        default: alu_result = 32'b0;
    endcase
end

assign zero = (alu_result == 32'b0);
endmodule