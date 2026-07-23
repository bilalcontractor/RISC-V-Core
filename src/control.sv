module control import cpu_core_pkg::*; (
    input  logic [6:0] op,
    input  logic [2:0] func3,
    input  logic [6:0] func7,
    input  logic alu_zero,
    input  logic alu_last,
    input  logic trap,
    input  logic [31:0] instruction,
    input  logic i_cache_stall,
    // Candidate faulting addresses used for misalignment detection:
    //   second_adder_addr = instruction-fetch target (branch/jal/jalr)
    //   alu_addr          = load/store effective address
    input  exception_target_addr_type exception_target_addr,

    output alu_control_type alu_control,
    output imm_source_type imm_source,
    output logic mem_write,
    output logic mem_read,
    output logic reg_write,
    output logic alu_source,
    output write_back_source_type write_back_source,
    output pc_source_type pc_source,
    output logic second_add_source,
    output logic csr_write_back_source,
    output logic csr_write_enable,
    output logic mret,
    output logic exception,
    output logic [30:0] exception_cause
);

    // Main Decoder
    alu_op_type alu_op;
    logic branch;          // static: this instruction is a branch type
    logic jump;            // static: unconditional jump (jal)
    logic jalr;
    logic assert_branch;   // dynamic: the branch condition currently holds
    always_comb begin
        // defaults so every signal is driven on every path (no latches)
        reg_write = 1'b0;
        imm_source = IMM_I_TYPE;
        mem_write = 1'b0;
        alu_op = ALU_OP_LOAD_STORE;
        alu_source = 1'b0; // reg2
        write_back_source = WB_ALU_RESULT;
        jump = 1'b0;
        second_add_source = 1'b0;
        jalr = 1'b0;
        mem_read = 1'b0;
        csr_write_enable = 1'b0;
        csr_write_back_source = 1'b0;
        mret = 1'b0;
        branch = 1'b0;

        // exception / exception_cause are owned by the instruction-validity
        // block below (single driver), so the main decoder does not touch them.

        case (op)
            // I type(lw)
            OPCODE_I_TYPE_LOAD : begin // opcode for load
                reg_write = 1'b1; // writing to a register (the data we load)
                imm_source = IMM_I_TYPE; // tell signext to use I-type formatting
                mem_write = 1'b0; // not writing to memory
                alu_op = ALU_OP_LOAD_STORE; // used in second ALU decoder block
                alu_source = 1'b1; // immediate, for address calc
                write_back_source = WB_MEM_READ; // mem_read, the loaded data
                branch = 1'b0;
                jump = 1'b0;
                mem_read = 1'b1;
            end
            // S type(sw)
            OPCODE_S_TYPE : begin // opcode
                reg_write = 1'b0; // not writing to register
                imm_source = IMM_S_TYPE; // tell signext to use S-type formatting
                mem_write = 1'b1; // writing to memory
                alu_op = ALU_OP_LOAD_STORE; // used for ALU, same as I type
                alu_source = 1'b1; // immediate, for address calc
                branch = 1'b0;
                jump = 1'b0;
            end
            // R type. Note no immediate
            OPCODE_R_TYPE : begin
                reg_write = 1'b1; // writing to register
                mem_write = 1'b0; // not writing to memory
                alu_op = ALU_OP_MATH;
                alu_source = 1'b0; // reg2
                write_back_source = WB_ALU_RESULT; // alu_result
                branch = 1'b0;
                jump = 1'b0;
            end
            // B type(beq)
            OPCODE_B_TYPE: begin
                reg_write = 1'b0; // not writing to register
                imm_source = IMM_B_TYPE;
                alu_source = 1'b0;
                mem_write = 1'b0;
                alu_op = ALU_OP_BRANCHES;
                branch = 1'b1; // We will have the possibility of branching
                jump = 1'b0;
            end
            // J type(jal)
            OPCODE_J_TYPE: begin
                reg_write = 1'b1;
                imm_source = IMM_J_TYPE;
                mem_write = 1'b0;
                write_back_source = WB_PC_PLUS_4; // pc + 4
                branch = 1'b0;
                jump = 1'b1; // jump flag on
            end
            // ALU I type(addi)
            OPCODE_I_TYPE_ALU: begin
                reg_write = 1'b1; // writing to register
                imm_source = IMM_I_TYPE; // I type formatting
                alu_source = 1'b1; // Immediate is the 2nd ALU operand
                mem_write = 1'b0; // not touching memory
                alu_op = ALU_OP_MATH;
                write_back_source = WB_ALU_RESULT; // not a memory read, not writing
                branch = 1'b0;
                jump = 1'b0;
            end
            // U-type
            OPCODE_U_TYPE_LUI, OPCODE_U_TYPE_AUIPC : begin
                imm_source = IMM_U_TYPE;
                mem_write = 1'b0;
                reg_write = 1'b1;
                write_back_source = WB_SECOND_ADD;
                branch = 1'b0;
                jump = 1'b0;
                case(op[5])
                    1'b1: second_add_source = 1'b1; // lui
                    1'b0: second_add_source = 1'b0; // auipc
                endcase
            end
            // I type jump(jalr)
            OPCODE_J_TYPE_JALR: begin
                reg_write = 1'b1;
                imm_source = IMM_I_TYPE; // I-type offset
                alu_source = 1'b1; // src2 = immediate
                alu_op = ALU_OP_LOAD_STORE; // ADD --> rs1 + offset
                mem_write = 1'b0;
                write_back_source = WB_PC_PLUS_4;
                branch = 1'b0; // No branching
                jump = 1'b0; // Want jalr, not jump
                jalr = 1'b1;
            end
            // CSR instructions
            OPCODE_CSR: begin
                case (func3) 
                    // ECALL + EBREAK -> Traps
                    3'b000: begin
                        // ECALL/EBREAK illegal-vs-trap handling lives in the
                        // instruction-validity block below; here we only need MRET.
                        if (instruction[31:20] == SYSTEM_MRET) begin // MRET
                            mret = 1'b1;
                        end
                    end

                    // Actual CSR instructions
                    3'b001, 3'b010, 3'b011, 3'b101, 3'b110, 3'b111: begin
                        imm_source = IMM_CSR_TYPE;
                        mem_write = 1'b0;
                        reg_write = 1'b1;
                        write_back_source = WB_CSR_READ;
                        // Determine write back source from MSB of func3
                        csr_write_back_source = func3[2];
                        csr_write_enable = 1'b1;
                    end

                    default: ;
                endcase
            end
            default: begin
                reg_write = 1'b0;
                imm_source = IMM_I_TYPE;
                mem_write = 1'b0;
                alu_op = ALU_OP_LOAD_STORE;
            end
        endcase
    end

    // True when `addr` is not naturally aligned for the access width in `func3`.
    // Byte accesses (LB/LBU/SB) can never be misaligned.
    function automatic logic ls_misaligned(input logic [2:0] func3, input logic [31:0] addr);
        case (func3)
            FUNC3_WORD:                       ls_misaligned = (addr % 4 != 0);
            FUNC3_HALFWORD, FUNC3_HALFWORD_U: ls_misaligned = (addr % 2 != 0);
            default:                          ls_misaligned = 1'b0;
        endcase
    endfunction

    // The instruction-fetch target must be 4-byte aligned (no compressed ISA).
    logic instr_target_misaligned;
    assign instr_target_misaligned = (exception_target_addr.second_adder_addr % 4 != 0);

    // Determine validity of instructions -> illegal-instruction detection + misalignment.
    always_comb begin
        exception       = ~i_cache_stall;
        exception_cause = EXC_ILLEGAL_INSTR;

        case (op)
            OPCODE_I_TYPE_LOAD: begin
                if ((func3 == 3'b000) || // LB
                    (func3 == 3'b001) || // LH
                    (func3 == 3'b010) || // LW
                    (func3 == 3'b100) || // LBU
                    (func3 == 3'b101)    // LHU
                ) begin
                    exception = 1'b0;
        
                    if (ls_misaligned(func3, exception_target_addr.alu_addr)) begin
                        exception       = 1'b1;
                        exception_cause = EXC_LOAD_ADDR_MISALIGNED;
                    end
                end
            end

            OPCODE_I_TYPE_ALU: begin
                if ((func3 == 3'b000) || // ADDI
                    (func3 == 3'b010) || // SLTI
                    (func3 == 3'b011) || // SLTIU
                    (func3 == 3'b100) || // XORI
                    (func3 == 3'b110) || // ORI
                    (func3 == 3'b111) || // ANDI
                    (func3 == 3'b001 && func7 == 7'd0) ||                       // SLLI
                    (func3 == 3'b101 && (func7 == 7'd0 || func7 == 7'b0100000)) // SRLI, SRAI
                ) exception = 1'b0;
            end

            OPCODE_S_TYPE: begin
                if ((func3 == 3'b000) || // SB
                    (func3 == 3'b001) || // SH
                    (func3 == 3'b010)    // SW
                ) begin
                    exception = 1'b0;
                   
                    if (ls_misaligned(func3, exception_target_addr.alu_addr)) begin
                        exception       = 1'b1;
                        exception_cause = EXC_STORE_ADDR_MISALIGNED;
                    end
                end
            end

            OPCODE_R_TYPE: begin
                if ((func3 == 3'b000 && (func7 == 7'd0 || func7 == 7'b0100000)) || // ADD, SUB
                    (func3 == 3'b001 && func7 == 7'd0) || // SLL
                    (func3 == 3'b010 && func7 == 7'd0) || // SLT
                    (func3 == 3'b011 && func7 == 7'd0) || // SLTU
                    (func3 == 3'b100 && func7 == 7'd0) || // XOR
                    (func3 == 3'b101 && (func7 == 7'd0 || func7 == 7'b0100000)) || // SRL, SRA
                    (func3 == 3'b110 && func7 == 7'd0) || // OR
                    (func3 == 3'b111 && func7 == 7'd0)    // AND
                ) exception = 1'b0;
            end

            OPCODE_B_TYPE: begin
                if ((func3 == 3'b000) || // BEQ
                    (func3 == 3'b001) || // BNE
                    (func3 == 3'b100) || // BLT
                    (func3 == 3'b101) || // BGE
                    (func3 == 3'b110) || // BLTU
                    (func3 == 3'b111)    // BGEU
                ) begin
                    exception = 1'b0;
                    // Only a TAKEN branch redirects the fetch, so only a taken
                    // branch to a misaligned target faults.
                    if (assert_branch && instr_target_misaligned) begin
                        exception       = 1'b1;
                        exception_cause = EXC_INSTR_ADDR_MISALIGNED;
                    end
                end
            end

            // JAL: no func3/func7 constraint. Always taken -> always redirects.
            OPCODE_J_TYPE: begin
                exception = 1'b0;
                if (instr_target_misaligned) begin
                    exception       = 1'b1;
                    exception_cause = EXC_INSTR_ADDR_MISALIGNED;
                end
            end

            // JALR: func3 must be 000. Always taken -> always redirects.
            OPCODE_J_TYPE_JALR: begin
                if (func3 == 3'b000) begin
                    exception = 1'b0;
                    if (instr_target_misaligned) begin
                        exception       = 1'b1;
                        exception_cause = EXC_INSTR_ADDR_MISALIGNED;
                    end
                end
            end

            // LUI / AUIPC: no func3/func7 constraint
            OPCODE_U_TYPE_LUI,
            OPCODE_U_TYPE_AUIPC: exception = 1'b0;

            OPCODE_CSR: begin
                case (func3)
                    3'b000: begin
                        // ECALL/EBREAK are legal instructions that deliberately
                        // trap with their own cause; MRET is legal (handled in the
                        // main decoder). Anything else with func3==000 is illegal.
                        if (instruction[31:20] == SYSTEM_ECALL) begin
                            exception       = 1'b1;
                            exception_cause = EXC_ECALL_M;
                        end
                        else if (instruction[31:20] == SYSTEM_EBREAK) begin
                            exception       = 1'b1;
                            exception_cause = EXC_BREAKPOINT;
                        end
                        else if (instruction[31:20] == SYSTEM_MRET) begin
                            exception = 1'b0;
                        end
                        // else: leave as illegal
                    end
                    // CSRRW/S/C and their immediate variants; func3==100 is illegal
                    3'b001, 3'b010, 3'b011,
                    3'b101, 3'b110, 3'b111: exception = 1'b0;
                    default: ; // func3 == 100 -> illegal
                endcase
            end

            default: ; // unknown opcode -> illegal (exception stays asserted)
        endcase
    end

    // ALU Decoder
    always_comb begin
        case(alu_op)
            // LW, SW
            ALU_OP_LOAD_STORE: alu_control = ALU_ADD;
            // R types, I types
            ALU_OP_MATH : begin
                case (func3)
                    FUNC3_ADD_SUB: begin
                        // Either R type(add or sub) or I type(addi)
                        if (op == OPCODE_R_TYPE) begin // If R type
                            alu_control = func7[5] ? ALU_SUB : ALU_ADD; // SUB : ADD
                        end else begin
                            alu_control = ALU_ADD; // ADDI
                        end
                    end
                    FUNC3_AND:     alu_control = ALU_AND; // AND
                    FUNC3_OR:      alu_control = ALU_OR; // OR
                    FUNC3_XOR:     alu_control = ALU_XOR; // XOR/XORI
                    FUNC3_SLT:     alu_control = ALU_SLT; // SLTI
                    FUNC3_SLTU:    alu_control = ALU_SLTU; // SLTIU
                    FUNC3_SLL:     alu_control = ALU_SLL; // SLLI
                    FUNC3_SRL_SRA: alu_control = (func7[5]) ? ALU_SRA : ALU_SRL; // SRAI : SRLI
                    default:    alu_control = ALU_SLTU; // Everything else
                endcase
            end
            // B type
            ALU_OP_BRANCHES: begin
                case (func3)
                    FUNC3_BEQ, FUNC3_BNE:   alu_control = ALU_SUB;  // BEQ/BNE   -> SUB (use zero flag)
                    FUNC3_BLT, FUNC3_BGE:   alu_control = ALU_SLT;  // BLT/BGE   -> signed SLT (use last bit)
                    FUNC3_BLTU, FUNC3_BGEU: alu_control = ALU_SLTU; // BLTU/BGEU -> unsigned SLT (use last bit)
                    default:          alu_control = ALU_SUB;  // fall back to SUB
                endcase
            end
            // Everything else
            default: alu_control = ALU_SLTU;
        endcase
    end

    // Branch resolution: is the branch condition satisfied given the ALU flags?
    always_comb begin
        case (func3)
            FUNC3_BEQ:  assert_branch = alu_zero;   // beq
            FUNC3_BNE:  assert_branch = ~alu_zero;  // bne
            FUNC3_BLT:  assert_branch = alu_last;   // blt
            FUNC3_BGE:  assert_branch = ~alu_last;  // bge
            FUNC3_BLTU: assert_branch = alu_last;   // bltu
            FUNC3_BGEU: assert_branch = ~alu_last;  // bgeu
            default: assert_branch = 1'b0;
        endcase
    end

    //// Redirect the PC only on a real branch whose condition holds, or on a jump(jal/jalr)
    always_comb begin
        if (trap) pc_source = PC_MTVEC;

        else if (mret) pc_source = PC_MEPC;

        else if (jalr) pc_source = PC_ALU_RESULT; // jalr --> alu_result

        else if ((assert_branch && branch) | jump) pc_source = PC_TARGET; // branch/jal --> pc_target

        else pc_source = PC_PLUS_4; // pc + 4
    end

endmodule
