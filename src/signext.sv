module signext (
    input logic [24:0] raw_src,
    input logic [1:0] imm_source,
    output logic [31:0] immediate
);

logic [11:0] gathered_imm;

always_comb begin
    case(imm_source) 
        //I types
        2'b00: gathered_imm = raw_src[24:13];
        //S types
        2'b01 : gathered_imm = {raw_src[24:18], raw_src[4:0]};
        //B types
        2'b10 : gathered_imm = {raw_src[0], raw_src[23:18], raw_src[4:1], 1'b0};
        default: gathered_imm = 12'b0;
    endcase
end

//Different immediates if instruction type is B type or anything else
assign immediate = (imm_source == 2'b10) ? {{20{raw_src[24]}}, gathered_imm} : 
    {{20{gathered_imm[11]}}, gathered_imm};

endmodule