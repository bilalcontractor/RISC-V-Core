module control import cpu_core_pkg::*; (
    input  logic [6:0] op,
    input  logic [2:0] func3,
    input  logic [6:0] func7,
    input  logic alu_zero,
    input  logic alu_last,

    output alu_control_type alu_control,
    output imm_source_type imm_source,
    output logic mem_write,
    output logic mem_read,
    output logic reg_write,
    output logic alu_source,
    output write_back_source_type write_back_source,
    output pc_source_type pc_source,
    output logic second_add_source
);

    //Main Decoder
    alu_op_type alu_op;
    logic branch;          //static: this instruction is a branch type
    logic jump;            //static: unconditional jump (jal)
    logic jalr;
    logic assert_branch;   //dynamic: the branch condition currently holds
    always_comb begin
        //defaults so every signal is driven on every path (no latches)
        reg_write = 1'b0;
        imm_source = IMM_I_TYPE;
        mem_write = 1'b0;
        alu_op = ALU_OP_LOAD_STORE;
        alu_source = 1'b0; //reg2
        write_back_source = WB_ALU_RESULT;
        jump = 1'b0;
        second_add_source = 1'b0;
        jalr = 1'b0;
        mem_read = 1'b0;
        case (op)
            //I type(lw)
            OPCODE_I_TYPE_LOAD : begin //opcode for load
                reg_write = 1'b1; //writing to a register (the data we load)
                imm_source = IMM_I_TYPE; //tell signext to use I-type formatting
                mem_write = 1'b0; //not writing to memory
                alu_op = ALU_OP_LOAD_STORE; //used in second ALU decoder block
                alu_source = 1'b1; //immediate, for address calc
                write_back_source = WB_MEM_READ; //mem_read, the loaded data
                branch = 1'b0;
                jump = 1'b0;
                mem_read = 1'b1;
            end
            //S type(sw)
            OPCODE_S_TYPE : begin //opcode
                reg_write = 1'b0; //not writing to register
                imm_source = IMM_S_TYPE; //tell signext to use S-type formatting
                mem_write = 1'b1; //writing to memory
                alu_op = ALU_OP_LOAD_STORE; //used for ALU, same as I type
                alu_source = 1'b1; //immediate, for address calc
                branch = 1'b0;
                jump = 1'b0;
            end
            //R type. Note no immediate
            OPCODE_R_TYPE : begin
                reg_write = 1'b1; //writing to register
                mem_write = 1'b0; //not writing to memory
                alu_op = ALU_OP_MATH;
                alu_source = 1'b0; //reg2
                write_back_source = WB_ALU_RESULT; //alu_result
                branch = 1'b0;
                jump = 1'b0;
            end
            //B type(beq)
            OPCODE_B_TYPE: begin
                reg_write = 1'b0; //not writing to register
                imm_source = IMM_B_TYPE;
                alu_source = 1'b0;
                mem_write = 1'b0;
                alu_op = ALU_OP_BRANCHES;
                branch = 1'b1; //We will have the possibility of branching
                jump = 1'b0;
            end
            //J type(jal)
            OPCODE_J_TYPE: begin
                reg_write = 1'b1;
                imm_source = IMM_J_TYPE;
                mem_write = 1'b0;
                write_back_source = WB_PC_PLUS_4; //pc + 4
                branch = 1'b0;
                jump = 1'b1; //jump flag on
            end
            //ALU I type(addi)
            OPCODE_I_TYPE_ALU: begin
                reg_write = 1'b1; //writing to register
                imm_source = IMM_I_TYPE; //I type formatting
                alu_source = 1'b1; //Immediate is the 2nd ALU operand
                mem_write = 1'b0; //not touching memory
                alu_op = ALU_OP_MATH;
                write_back_source = WB_ALU_RESULT; //not a memory read, not writing
                branch = 1'b0;
                jump = 1'b0;
            end
            //U-type
            OPCODE_U_TYPE_LUI, OPCODE_U_TYPE_AUIPC : begin
                imm_source = IMM_U_TYPE;
                mem_write = 1'b0;
                reg_write = 1'b1;
                write_back_source = WB_SECOND_ADD;
                branch = 1'b0;
                jump = 1'b0;
                case(op[5])
                    1'b1: second_add_source = 1'b1; //lui
                    1'b0: second_add_source = 1'b0; //auipc
                endcase
            end
            //I type jump(jalr)
            OPCODE_J_TYPE_JALR: begin
                reg_write = 1'b1;
                imm_source = IMM_I_TYPE; //I-type offset
                alu_source = 1'b1; //src2 = immediate
                alu_op = ALU_OP_LOAD_STORE; //ADD --> rs1 + offset
                mem_write = 1'b0;
                write_back_source = WB_PC_PLUS_4;
                branch = 1'b0; //No branching
                jump = 1'b0; //Want jalr, not jump
                jalr = 1'b1;
            end
            default: begin
                reg_write = 1'b0;
                imm_source = IMM_I_TYPE;
                mem_write = 1'b0;
                alu_op = ALU_OP_LOAD_STORE;
                branch = 1'b0;
            end
        endcase
    end

    //ALU Decoder
    always_comb begin
        case(alu_op)
            //LW, SW
            ALU_OP_LOAD_STORE: alu_control = ALU_ADD;
            //R types, I types
            ALU_OP_MATH : begin
                case (func3)
                    F3_ADD_SUB: begin
                        // Either R type(add or sub) or I type(addi)
                        if (op == OPCODE_R_TYPE) begin //If R type
                            alu_control = func7[5] ? ALU_SUB : ALU_ADD; //SUB : ADD
                        end else begin
                            alu_control = ALU_ADD; //ADDI
                        end
                    end
                    F3_AND:     alu_control = ALU_AND; //AND
                    F3_OR:      alu_control = ALU_OR; //OR
                    F3_XOR:     alu_control = ALU_XOR; //XOR/XORI
                    F3_SLT:     alu_control = ALU_SLT; //SLTI
                    F3_SLTU:    alu_control = ALU_SLTU; //SLTIU
                    F3_SLL:     alu_control = ALU_SLL; //SLLI
                    F3_SRL_SRA: alu_control = (func7[5]) ? ALU_SRA : ALU_SRL; //SRAI : SRLI
                    default:    alu_control = ALU_SLTU; //Everything else
                endcase
            end
            //B type
            ALU_OP_BRANCHES: begin
                case (func3)
                    F3_BEQ, F3_BNE:   alu_control = ALU_SUB;  //BEQ/BNE   -> SUB (use zero flag)
                    F3_BLT, F3_BGE:   alu_control = ALU_SLT;  //BLT/BGE   -> signed SLT (use last bit)
                    F3_BLTU, F3_BGEU: alu_control = ALU_SLTU; //BLTU/BGEU -> unsigned SLT (use last bit)
                    default:          alu_control = ALU_SUB;  //fall back to SUB
                endcase
            end
            //Everything else
            default: alu_control = ALU_SLTU;
        endcase
    end

    //Branch resolution: is the branch condition satisfied given the ALU flags?
    always_comb begin
        case (func3)
            F3_BEQ:  assert_branch = alu_zero;   //beq
            F3_BNE:  assert_branch = ~alu_zero;  //bne
            F3_BLT:  assert_branch = alu_last;   //blt
            F3_BGE:  assert_branch = ~alu_last;  //bge
            F3_BLTU: assert_branch = alu_last;   //bltu
            F3_BGEU: assert_branch = ~alu_last;  //bgeu
            default: assert_branch = 1'b0;
        endcase
    end

    // //Redirect the PC only on a real branch whose condition holds, or on a jump(jal/jalr)
    always_comb begin
        if (jalr) pc_source = PC_ALU_RESULT; //jalr --> alu_result
        else if ((assert_branch && branch) | jump) pc_source = PC_TARGET; //branch/jal --> pc_target
        else pc_source = PC_PLUS_4; //pc + 4
    end

endmodule
