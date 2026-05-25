module control (
    input logic [6:0] op,
    input logic [2:0] func3,
    input logic [6:0] func7,
    input logic alu_zero,

    output logic [2:0] alu_control,
    output logic [1:0] imm_source,
    output logic mem_write,
    output logic reg_write,
    output logic alu_source,
    output logic [1:0] write_back_source,
    output logic pc_source
); 

//Main Decoder
logic [1:0] alu_op;
logic branch;          //static: this instruction is a branch type
logic jump;            //static: unconditional jump (jal)
logic assert_branch;   //dynamic: the branch condition currently holds
always_comb begin
    //defaults so every signal is driven on every path (no latches)
    reg_write = 1'b0;
    imm_source = 2'b00;
    mem_write = 1'b0;
    alu_op = 2'b00;
    alu_source = 1'b0; //reg2
    write_back_source = 2'b00; //alu_result
    jump = 1'b0;
    case (op)
        //I type(lw)
        7'b0000011 : begin //opcode for load
            reg_write = 1'b1; //writing to a register (the data we load)
            imm_source = 2'b00; //tell signext to use I-type formatting
            mem_write = 1'b0; //not writing to memory
            alu_op = 2'b00; //used in second ALU decoder block
            alu_source = 1'b1; //immediate, for address calc
            write_back_source = 2'b01; //mem_read, the loaded data
            branch = 1'b0;
            jump = 1'b0;
        end
        //S type(sw)
        7'b0100011 : begin //opcode
            reg_write = 1'b0; //not writing to register
            imm_source = 2'b01; //tell signext to use S-type formatting
            mem_write = 1'b1; //writing to memory
            alu_op = 2'b00; //used for ALU, same as I type
            alu_source = 1'b1; //immediate, for address calc
            branch = 1'b0;
            jump = 1'b0;
        end
        //R type. Note no immediate
        7'b0110011 : begin
            reg_write = 1'b1; //writing to register
            mem_write = 1'b0; //not writing to memory
            alu_op = 2'b10;
            alu_source = 1'b0; //reg2
            write_back_source = 2'b00; //alu_result
            branch = 1'b0;
            jump = 1'b0;
        end
        //B type(beq)
        7'b1100011: begin
            reg_write = 1'b0; //not writing to register
            imm_source = 2'b10;
            alu_source = 1'b0;
            mem_write = 1'b0;
            alu_op = 2'b01;
            branch = 1'b1; //We will have the possibility of branching
            jump = 1'b0;
        end
        //J type(jal)
        7'b1101111: begin
            reg_write = 1'b1; 
            imm_source = 2'b11;
            mem_write = 1'b0;
            write_back_source = 2'b10; //pc + 4
            branch = 1'b0;
            jump = 1'b1; //jump flag on
        end
        //ALU I type(addi) 
        7'b0010011: begin
            reg_write = 1'b1; //writing to register
            imm_source = 2'b00; //I type formatting 
            alu_source = 1'b1; //Immediate is the 2nd ALU operand
            mem_write = 1'b0; //not touching memory
            alu_op = 2'b10;
            write_back_source = 2'b00; //not a memory read, not writing
            branch = 1'b0;
            jump = 1'b0;
        end
        default: begin
            reg_write = 1'b0;
            imm_source = 2'b00;
            mem_write = 1'b0;
            alu_op = 2'b00;
            branch = 1'b0;
        end
    endcase
end

//ALU Decoder
always_comb begin
    case(alu_op)
        //LW, SW
        2'b00: alu_control = 3'b000;
        //R types
        2'b10 : begin
            case (func3)
                3'b000 : alu_control = 3'b000; //ADD
                3'b111 : alu_control = 3'b010; //AND
                3'b110 : alu_control = 3'b011; //OR
                default : alu_control = 3'b111; //Everything else
            endcase
        end
        //B type --> BEQ
        2'b01 : alu_control = 3'b001;
        //Everything else
        default: alu_control = 3'b111;
    endcase
end

//Branch resolution: is the branch condition satisfied given the ALU flags?
//Computed for every instruction, so it MUST be gated by the opcode below.
always_comb begin
    case (func3)
        3'b000:  assert_branch = alu_zero;   //beq: taken if rs1 == rs2
        3'b001:  assert_branch = ~alu_zero;  //bne: taken if rs1 != rs2
        default: assert_branch = 1'b0;
    endcase
end

//Redirect the PC only on a real branch whose condition holds, or on a jump
assign pc_source = (assert_branch & branch) | jump;

endmodule
