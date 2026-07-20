`timescale 1ns/1ps

package cpu_core_pkg;
    // Instruction Op Codes
    typedef enum logic [6:0] {
        OPCODE_R_TYPE        = 7'b0110011,
        OPCODE_I_TYPE_ALU    = 7'b0010011,
        OPCODE_I_TYPE_LOAD   = 7'b0000011,
        OPCODE_S_TYPE        = 7'b0100011,
        OPCODE_B_TYPE        = 7'b1100011,
        OPCODE_U_TYPE_LUI    = 7'b0110111,
        OPCODE_U_TYPE_AUIPC  = 7'b0010111,
        OPCODE_J_TYPE        = 7'b1101111,
        OPCODE_J_TYPE_JALR   = 7'b1100111,
        OPCODE_CSR           = 7'b1110011
    } opcode_type;

    // ALU Op Codes for ALU decoder
    typedef enum logic [1:0] {
        ALU_OP_LOAD_STORE  = 2'b00,
        ALU_OP_BRANCHES    = 2'b01,
        ALU_OP_MATH        = 2'b10
    } alu_op_type;

    // MATH func3 --> R & I Type Instructions
    typedef enum logic [2:0] {
        FUNC3_ADD_SUB  = 3'b000,
        FUNC3_SLL      = 3'b001,
        FUNC3_SLT      = 3'b010,
        FUNC3_SLTU     = 3'b011,
        FUNC3_XOR      = 3'b100,
        FUNC3_SRL_SRA  = 3'b101,
        FUNC3_OR       = 3'b110,
        FUNC3_AND      = 3'b111
    } func3_type;

    // Func3 Branches
    typedef enum logic [2:0] {
        FUNC3_BEQ  = 3'b000,
        FUNC3_BNE  = 3'b001,
        FUNC3_BLT  = 3'b100,
        FUNC3_BGE  = 3'b101,
        FUNC3_BLTU  = 3'b110,
        FUNC3_BGEU  = 3'b111
    } func3_branch_type;

    // LOAD & STORES FUNC3
    typedef enum logic [2:0] {
        FUNC3_WORD = 3'b010,
        FUNC3_BYTE = 3'b000,
        FUNC3_BYTE_U = 3'b100,
        FUNC3_HALFWORD = 3'b001,
        FUNC3_HALFWORD_U = 3'b101
    } func3_load_store_type;

    // FUNC7 for shifts
    typedef enum logic [6:0] {
        FUNC7_SLL_SRL  = 7'b0000000,
        FUNC7_SRA  = 7'b0100000
    } func7_shift_type;

    // FUNC7 for R-Types
    typedef enum logic [6:0] {
        FUNC7_ADD  = 7'b0000000,
        FUNC7_SUB  = 7'b0100000
    } func7_r_type;

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
        IMM_U_TYPE = 3'b100,
        IMM_CSR_TYPE = 3'b101
    } imm_source_type;

    // Write-back source mux select (control --> cpu write-back mux)
    typedef enum logic [2:0] {
        WB_ALU_RESULT = 3'b000, // R-type / I-type ALU ops
        WB_MEM_READ   = 3'b001, // loads
        WB_PC_PLUS_4  = 3'b010, // jal / jalr link register
        WB_SECOND_ADD = 3'b011, // auipc / lui
        WB_CSR_READ   = 3'b100  // CSR instructions (old CSR value -> rd)
    } write_back_source_type;

    // Next-PC mux select (control --> cpu next-PC mux)
    typedef enum logic [1:0] {
        PC_PLUS_4     = 2'b00, // sequential
        PC_TARGET     = 2'b01, // branch / jal
        PC_ALU_RESULT = 2'b10  // jalr
    } pc_source_type;

    // CSR addresses (machine-mode, custom read-write region 0x7C0-0x7FF)
    typedef enum logic [11:0] {
        CSR_FLUSH_CACHE         = 12'h7C0,  // flush request into the cache
        CSR_NON_CACHABLE_BASE   = 12'h7C1,  // base address of non-cachable range
        CSR_NON_CACHABLE_LIMIT  = 12'h7C2,  // limit address of non-cachable range

        // Standard machine-mode trap-handling CSRs
        CSR_MSTATUS             = 12'h300,  // machine status
        CSR_MIE                 = 12'h304,  // machine interrupt-enable
        CSR_MTVEC               = 12'h305,  // machine trap-vector base address
        CSR_MEPC                = 12'h341,  // machine exception program counter
        CSR_MCAUSE              = 12'h342,  // machine trap cause
        CSR_MTVAL               = 12'h343,  // machine trap value (address/instruction)
        CSR_MIP                 = 12'h344   // machine interrupt-pending
    } csr_address_type;

    // Exception causes : mcause[31] == 0
    typedef enum logic [30:0] {
        EXC_INSTR_ADDR_MISALIGNED = 31'd0,  // misaligned jump/branch target
        EXC_ILLEGAL_INSTR         = 31'd2,  // illegal instruction
        EXC_BREAKPOINT            = 31'd3,  // ebreak
        EXC_LOAD_ADDR_MISALIGNED  = 31'd4,  // misaligned load address
        EXC_STORE_ADDR_MISALIGNED = 31'd6,  // misaligned store address
        EXC_ECALL_M               = 31'd11  // ecall taken from machine mode
    } exception_cause_type;

    // Interrupt causes : mcause[31] == 1
    typedef enum logic [30:0] {
        INT_M_SOFTWARE = 31'd3,
        INT_M_TIMER    = 31'd7,
        INT_M_EXTERNAL = 31'd11
    } interrupt_cause_type;

   
    typedef struct packed {
        logic [31:0] second_adder_addr; // branch/jump target adder result
        logic [31:0] alu_addr;          // ALU-computed load/store address
    } exception_target_addr_type;

    typedef enum logic [3:0] {
        IDLE,                  // cache is not doing anything . stall not asserted
        // AXI (burst) states : move whole cache lines to/from main memory
        SENDING_WRITE_REQUEST, // cache missed and cache was dirty. currently sending write request to memory
        SENDING_WRITE_DATA,    // cache sending data burst to main memory
        WAITING_WRITE_RECIEVE, // cache waiting for write confirmation from main memory
        SENDING_READ_REQUEST,  // cache missed. now send read request to get new data from main memory into cache
        RECIEVING_READ_DATA,   // cache the data incoming from main memory
        // AXI-Lite (single-beat) states : MMIO bypass for non-cachable addresses
        LITE_SENDING_WRITE_REQUEST, // non-cachable write: sending write address
        LITE_SENDING_WRITE_DATA,    // non-cachable write: sending the single data beat
        LITE_WAITING_WRITE_RECIEVE, // non-cachable write: waiting for write confirmation
        LITE_SENDING_READ_REQUEST,  // non-cachable read: sending read address
        LITE_RECIEVING_READ_DATA    // non-cachable read: receiving the single data beat
    } cache_state_type;

endpackage