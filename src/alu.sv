module alu import cpu_core_pkg::*; (
    // In
    input  alu_control_type alu_control,
    input  logic [31:0] src1,
    input  logic [31:0] src2,
    // Out
    output logic [31:0] alu_result,
    output logic zero,
    output logic alu_last
);

    assign alu_last = alu_result[0]; // last bit of result
    assign zero = (alu_result == 32'b0);

    always_comb begin
        case(alu_control)
            ALU_ADD:  alu_result = src1 + src2; // ADD
            ALU_AND:  alu_result = src1 & src2; // AND
            ALU_OR:   alu_result = src1 | src2; // OR
            ALU_SUB:  alu_result = src1 + (~src2 + 1'b1); // SUB. Use two's complement(rs1 - rs2)
            ALU_SLT:  alu_result = {31'b0, $signed(src1) < $signed(src2)}; // src1 < src2
            ALU_SLTU: alu_result = {31'b0, src1 < src2}; // src1 < src2(UNSIGNED)
            ALU_XOR:  alu_result = src1 ^ src2; // XOR

            // Shifts by lowest 5 bits --> src2[4:0]
            ALU_SLL:  alu_result = src1 << src2[4:0]; // SLLI --> shift left logical immediate
            ALU_SRA:  alu_result = $signed(src1) >>> src2[4:0]; // SRAI --> shift right arithmetic immediate
            ALU_SRL:  alu_result = src1 >> src2[4:0]; // SRLI --> shift right logical immediate

            default: alu_result = 32'b0;
        endcase
    end

endmodule