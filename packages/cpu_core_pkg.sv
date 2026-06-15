`timescale 1ns/1ps

package cpu_core_pkg;
    //Instruction Op Codes
    typedef enum logic [6:0] {
        OPCODE_R_TYPE        = 7'b0110011,
        OPCODE_I_TYPE_ALU    = 7'b0010011,
        OPCODE_I_TYPE_LOAD   = 7'b0000011,
        OPCODE_S_TYPE        = 7'b0100011,
        OPCODE_B_TYPE        = 7'b1100011,
        OPCODE_U_TYPE_LUI    = 7'b0110111,
        OPCODE_U_TYPE_AUIPC  = 7'b0010111,
        OPCODE_J_TYPE        = 7'b1101111,
        OPCODE_J_TYPE_JALR   = 7'b1100111
    } opcode_type;

    //ALU Op Codes for ALU decoder
    typedef enum logic [1:0] {
        ALU_OP_LOAD_STORE  = 2'b00,
        ALU_OP_BRANCHES    = 2'b01,
        ALU_OP_MATH        = 2'b10
    } alu_op_type;

    //MATH func3 --> R & I Type Instructions
    typedef enum logic [2:0] {
        F3_ADD_SUB  = 3'b000,
        F3_SLL      = 3'b001,
        F3_SLT      = 3'b010,
        F3_SLTU     = 3'b011,
        F3_XOR      = 3'b100,
        F3_SRL_SRA  = 3'b101,
        F3_OR       = 3'b110,
        F3_AND      = 3'b111
    } func3_type;

    //Func3 Branches
    typedef enum logic [2:0] {
    F3_BEQ  = 3'b000,
    F3_BNE  = 3'b001,
    F3_BLT  = 3'b100,
    F3_BGE  = 3'b101,
    F3_BLTU  = 3'b110,
    F3_BGEU  = 3'b111
    } func3_branch_type;

    // LOAD & STORES F3
    typedef enum logic [2:0] {
        F3_WORD = 3'b010,
        F3_BYTE = 3'b000,
        F3_BYTE_U = 3'b100,
        F3_HALFWORD = 3'b001,
        F3_HALFWORD_U = 3'b101
    } func3_load_store_type;

    // F7 for shifts
    typedef enum logic [6:0] {
        F7_SLL_SRL  = 7'b0000000,
        F7_SRA  = 7'b0100000
    } f7_shift_type;

    // F7 for R-Types
    typedef enum logic [6:0] {
        F7_ADD  = 7'b0000000,
        F7_SUB  = 7'b0100000
    } f7_r_type;

    // ALU control arithmetic
    typedef enum logic [3:0] {
        ALU_ADD = 4'b0000,
        ALU_SUB = 4'b0001,
        ALU_AND = 4'b0010,
        ALU_OR = 4'b0011,
        ALU_SLL = 4'b0100,
        ALU_SLT = 4'b0101,
        ALU_SRL = 4'b0110,
        ALU_SLTU = 4'b0111,
        ALU_XOR = 4'b1000,
        ALU_SRA = 4'b1001
    } alu_control_type;

    // Immediate format select (control --> signext)
    typedef enum logic [2:0] {
        IMM_I_TYPE = 3'b000,
        IMM_S_TYPE = 3'b001,
        IMM_B_TYPE = 3'b010,
        IMM_J_TYPE = 3'b011,
        IMM_U_TYPE = 3'b100
    } imm_source_type;

    // Write-back source mux select (control --> cpu write-back mux)
    typedef enum logic [1:0] {
        WB_ALU_RESULT = 2'b00, //R-type / I-type ALU ops
        WB_MEM_READ   = 2'b01, //loads
        WB_PC_PLUS_4  = 2'b10, //jal / jalr link register
        WB_SECOND_ADD = 2'b11  //auipc / lui
    } write_back_source_type;

    // Next-PC mux select (control --> cpu next-PC mux)
    typedef enum logic [1:0] {
        PC_PLUS_4     = 2'b00, //sequential
        PC_TARGET     = 2'b01, //branch / jal
        PC_ALU_RESULT = 2'b10  //jalr
    } pc_source_type;

    typedef enum logic [2:0] {
        IDLE,                  //cache is not doing anything . stall not asserted
        SENDING_WRITE_REQUEST, //cache missed and cache was dirty. currently sending write request to memory
        SENDING_WRITE_DATA,    //cache sending data burst to main memory
        WAITING_WRITE_RECIEVE, //cache waiting for write confirmation from main memory
        SENDING_READ_REQUEST,  //cache missed. now send read request to get new data from main memory into cache
        RECIEVING_READ_DATA    //cache the data incoming from main memory
    } cache_state_type;

endpackage