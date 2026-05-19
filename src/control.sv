module control (
    input logic [6:0] op,
    input logic [2:0] func3,
    input logic [6:0] func7,
    input logic alu_zero,

    output logic [2:0] alu_control,
    output logic [1:0] imm_source,
    output logic mem_write,
    output logic reg_write
); 

//Main Decoder
logic [1:0] alu_op;
always_comb begin
    case (op)
        //I type(lw)
        7'b0000011 : begin //opcode for load 
            reg_write = 1'b1; //writing to a register (the data we load)
            imm_source = 2'b00; //tell signext to use I-type formatting
            mem_write = 1'b0; //not writing to memory
            alu_op = 2'b00; //used in second ALU decoder block
        end
        //S type(sw)
        7'b0100011 : begin //opcode
            reg_write = 1'b0; //not writing to register
            imm_source = 2'b01; //tell signext to use S-type formatting
            mem_write = 1'b1; //writing to memory
            alu_op = 2'b00; //used for ALU, same as I type
        end
        default: begin
            reg_write = 1'b0;
            imm_source = 2'b00;
            mem_write = 1'b0;
            alu_op = 2'b00;
        end 
    endcase 
end

//ALU Decoder
always_comb begin
    case(alu_op)
        2'b00: alu_control = 3'b000;
        default: alu_control = 3'b111;
    endcase
end

endmodule