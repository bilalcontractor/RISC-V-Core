module control (
    input logic [6:0] op,
    input logic [2:0] func3,
    input logic [6:0] func7,
    input logic alu_zero,
    input logic alu_last,

    output logic [3:0] alu_control,
    output logic [2:0] imm_source,
    output logic mem_write,
    output logic reg_write,
    output logic alu_source,
    output logic [1:0] write_back_source,
    output logic pc_source,
    output logic second_add_source
); 

//Main Decoder
logic [1:0] alu_op;
logic branch;          //static: this instruction is a branch type
logic jump;            //static: unconditional jump (jal)
logic assert_branch;   //dynamic: the branch condition currently holds
always_comb begin
    //defaults so every signal is driven on every path (no latches)
    reg_write = 1'b0;
    imm_source = 3'b000;
    mem_write = 1'b0;
    alu_op = 2'b00;
    alu_source = 1'b0; //reg2
    write_back_source = 2'b00; //alu_result
    jump = 1'b0;
    second_add_source = 1'b0;
    case (op)
        //I type(lw)
        7'b0000011 : begin //opcode for load
            reg_write = 1'b1; //writing to a register (the data we load)
            imm_source = 3'b000; //tell signext to use I-type formatting
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
            imm_source = 3'b001; //tell signext to use S-type formatting
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
            imm_source = 3'b010;
            alu_source = 1'b0;
            mem_write = 1'b0;
            alu_op = 2'b01;
            branch = 1'b1; //We will have the possibility of branching
            jump = 1'b0;
        end
        //J type(jal)
        7'b1101111: begin
            reg_write = 1'b1; 
            imm_source = 3'b011;
            mem_write = 1'b0;
            write_back_source = 2'b10; //pc + 4
            branch = 1'b0;
            jump = 1'b1; //jump flag on
        end
        //ALU I type(addi) 
        7'b0010011: begin
            reg_write = 1'b1; //writing to register
            imm_source = 3'b000; //I type formatting
            alu_source = 1'b1; //Immediate is the 2nd ALU operand
            mem_write = 1'b0; //not touching memory
            alu_op = 2'b10;
            write_back_source = 2'b00; //not a memory read, not writing
            branch = 1'b0;
            jump = 1'b0;
        end
        //U-type
        7'b0110111, 7'b0010111 : begin
            imm_source = 3'b100;
            mem_write = 1'b0;
            reg_write = 1'b1;
            write_back_source = 2'b11;
            branch = 1'b0;
            jump = 1'b0;
            case(op[5])
                1'b1: second_add_source = 1'b1; //lui
                1'b0: second_add_source = 1'b0; //auipc
            endcase
        end
        default: begin
            reg_write = 1'b0;
            imm_source = 3'b000;
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
        2'b00: alu_control = 4'b0000;
        //R types, I types
        2'b10 : begin
            case (func3)
                // 3'b000: alu_control = 4'b0000; //ADD
                3'b000: begin
                    // Either R type(add or sub) or I type(addi)
                    if (op == 7'b0110011) begin //If R type
                        alu_control = func7[5] ? 4'b0001 : 4'b0000; //SUB : ADD
                    end else begin
                        alu_control = 4'b0000; //ADDI
                    end
                end
                3'b111: alu_control = 4'b0010; //AND
                3'b110: alu_control = 4'b0011; //OR
                3'b100: alu_control = 4'b1000; //XOR/XORI
                3'b010: alu_control = 4'b0101; //SLTI
                3'b011: alu_control = 4'b0111; //SLTIU
                3'b001: alu_control = 4'b0100; //SLLI
                3'b101: alu_control = (func7[5]) ? 4'b1001 : 4'b0110; //SRAI : SRLI
                default: alu_control = 4'b0111; //Everything else
            endcase
        end
        //B type
        2'b01: begin
            case (func3)
                3'b000, 3'b001: alu_control = 4'b0001; //BEQ/BNE   -> SUB (use zero flag)
                3'b100, 3'b101: alu_control = 4'b0101; //BLT/BGE   -> signed SLT (use last bit)
                3'b110, 3'b111: alu_control = 4'b0111; //BLTU/BGEU -> unsigned SLT (use last bit)
                default:        alu_control = 4'b0001; //fall back to SUB
            endcase
        end
        //Everything else
        default: alu_control = 4'b0111;
    endcase
end

//Branch resolution: is the branch condition satisfied given the ALU flags?
always_comb begin
    case (func3)
        3'b000:  assert_branch = alu_zero;   //beq
        3'b001:  assert_branch = ~alu_zero;  //bne
        3'b100:  assert_branch = alu_last;   //blt
        3'b101:  assert_branch = ~alu_last;  //bge
        3'b110:  assert_branch = alu_last;   //bltu
        3'b111:  assert_branch = ~alu_last;  //bgeu
        default: assert_branch = 1'b0;
    endcase
end

//Redirect the PC only on a real branch whose condition holds, or on a jump
assign pc_source = (assert_branch & branch) | jump;

endmodule
