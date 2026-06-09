module signext import cpu_core_pkg::*; (
    // IN
    input  logic [24:0] raw_src,
    input  imm_source_type imm_source,

    // OUT (immediate)
    output logic [31:0] immediate
);

always_comb begin
    case (imm_source)
        // For I-Types
        IMM_I_TYPE : immediate = {{20{raw_src[24]}}, raw_src[24:13]};
        // For S-types
        IMM_S_TYPE : immediate = {{20{raw_src[24]}},raw_src[24:18],raw_src[4:0]};
        // For B-types
        IMM_B_TYPE : immediate = {{20{raw_src[24]}},raw_src[0],raw_src[23:18],raw_src[4:1],1'b0};
        // For J-types
        IMM_J_TYPE : immediate = {{12{raw_src[24]}}, raw_src[12:5], raw_src[13],
            raw_src[23:14], 1'b0};
        //For U-types
        IMM_U_TYPE : immediate = {raw_src[24:5], 12'b0};
        default: immediate = 32'b0;
    endcase
end
    
endmodule