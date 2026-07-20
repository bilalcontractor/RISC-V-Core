module csrfile import cpu_core_pkg::*; (
    input logic clk,
    input logic rst_n,
    input logic [2:0] func3,        // CSR op: write / set / clear (csrrw / csrrs / csrrc)
    input logic [31:0] write_data,  // value coming from the source register (rs1)
    input logic write_enable,
    input logic [11:0] address,     // CSR address from the instruction immediate

    // Interrupts in
    input logic timer_interrupt,
    input logic software_interrupt,
    input logic external_interrupt,

    // PC of the instruction currently executing; latched into mepc on a trap
    input logic [31:0] current_core_pc,
    // Instruction word currently in flight; latched into mtval on an illegal instruction
    input logic [31:0] current_core_fetch_instr,
    // Candidate faulting addresses; latched into mtval on a misalignment
    input exception_target_addr_type exception_target_addr,

    // Signals from control
    input logic mret,               // MACHINE MODE RETURN FROM TRAP
    input logic exception,
    input logic [30:0] exception_cause, 

    output logic [31:0] read_data,  // current value of the addressed CSR (0 if unmapped)

    // CSR flags
    output logic flush_cache_flag,   // 1-cycle pulse telling the cache to flush
    output logic [31:0] non_cachable_base_address, // base address for non cachable range
    output logic [31:0] non_cachable_limit_address, // limit address for non cachable range

    output logic trap // Should we trap or not?
);

    logic [31:0] flush_cache, next_flush_cache;
    logic [31:0] non_cachable_base, next_non_cachable_base;
    logic [31:0] non_cachable_limit, next_non_cachable_limit;
    logic [31:0] write_back_to_csr; // value the addressed CSR would take

    // Trap handling CSRs
    logic [31:0] mstatus, next_mstatus; // MACHINE STATUS: global interrupt enable + saved state on a trap
    logic [31:0] mie, next_mie;         // MACHINE INTERRUPT ENABLE: per-source enable mask (timer/soft/ext)
    logic [31:0] mip, next_mip;         // MACHINE INTERRUPT PENDING: per-source pending flags (timer/soft/ext)
    logic [31:0] mtvec, next_mtvec;     // MACHINE TRAP VECTOR: base address the PC jumps to on a trap
    logic [31:0] mepc, next_mepc;       // MACHINE EXCEPTION PC: PC saved on trap entry, restored by mret
    logic [31:0] mcause, next_mcause;   // MACHINE CAUSE: why the trap fired (interrupt vs exception + code)
    logic [31:0] mtval, next_mtval;     // MACHINE TRAP VALUE: accompanies mcause, tells which address/instruction involved
    logic trap_taken;

    always_ff @(posedge clk) begin
        if (~rst_n) begin
            flush_cache <= 32'd0; 
            non_cachable_base <= 32'd0;
            non_cachable_limit <= 32'd0;

            // Traps
            mstatus <= 32'd0;
            mie <= 32'd0;
            mip <= 32'd0;
            mtvec <= 32'd0;
            mepc <= 32'd0;
            mcause <= 32'd0;
            mtval <= 32'd0;
            
            trap_taken <= 1'b0;
        end
        else begin
            flush_cache <= next_flush_cache;
            non_cachable_base <= next_non_cachable_base;
            non_cachable_limit <= next_non_cachable_limit;

            // Traps
            mstatus <= next_mstatus;
            mie <= next_mie;
            mip <= next_mip;
            mtvec <= next_mtvec;
            mepc <= next_mepc;
            mcause <= next_mcause;
            mtval <= next_mtval;

            trap_taken <= trap_taken;
            if (trap) trap_taken <= 1'b1;
            else if (mret) trap_taken <= 1'b0;
        end
    end

    // Trap CSR logic
    always_comb begin
        /* 
           mstatus
           bit 3 = MIE -> MACHINE INTERRUPT ENABLE
           bit 7 = MPIE -> MACHINE PREVIOUS INTERRUPT ENABLE       
        */
        next_mstatus = mstatus;
        if (trap) begin
            next_mstatus[7] = next_mstatus[3]; // Save currect value(MPIE = MIE)
            next_mstatus[3] = 0; // MIE = 0
        end
        else if (mret) begin
            next_mstatus[3] = next_mstatus[7]; // Restores old value when returning(MIE = MPIE)
        end
        else if (write_enable & (address == CSR_MSTATUS)) begin
            next_mstatus = write_back_to_csr;
        end

        // mie
        next_mie = mie;
        if (write_enable & (address == CSR_MIE)) begin
            next_mie = write_back_to_csr;
        end

        // mtvec
        next_mtvec = mtvec;
        if (write_enable & (address == CSR_MTVEC)) begin
            next_mtvec = write_back_to_csr;
        end

        // mip
        /*
           Each bit in mip is a seperate flag for a different interrupt source
           bit 3 = MSIP --> machine software interrupt pending bit
           bit 7 = MTIP --> machine timer interrupt pending bit
           bit 11 = MEIP --> machine external interrupt pending bit
           
           We bit shift the special interrupt bits(software_interrupt, 
           timer_interrupt, external_interrupt) into their respective positions, then do bitwise OR
           to combine everything into one vector
        */
        next_mip = (32'(software_interrupt) << 3) | (32'(timer_interrupt) << 7) 
            | (32'(external_interrupt) << 11);

        // mepc
        next_mepc = mepc;
        if (trap) begin
            next_mepc = current_core_pc;
        end
        else if (write_enable & (address == CSR_MEPC)) begin
            next_mepc = write_back_to_csr;
        end
        
        // mcause
        next_mcause = mcause; //mcause is a value based signal, not one hot encoding/bit based
        if (trap) begin
            if (|(mie & mip)) begin
                // If its an interrupt
                next_mcause[31] = 1;
                if (mip[11] && mie[11]) begin // External
                    next_mcause[30:0] = 31'd11;
                end
                else if (mip[7] && mie[7]) begin // Timer
                    next_mcause[30:0] = 31'd7;
                end
                else if (mip[3] && mie[3]) begin // Software
                    next_mcause[30:0] = 31'd3;
                end
            end

            else if (exception) begin
                next_mcause[31] = 0;
                next_mcause[30:0] = exception_cause;
            end
        end

        // mtval
        next_mtval = mtval;
        if (trap && exception) begin
            case (exception_cause)
                EXC_INSTR_ADDR_MISALIGNED: next_mtval = exception_target_addr.second_adder_addr;
                EXC_ILLEGAL_INSTR:         next_mtval = current_core_fetch_instr;
                EXC_LOAD_ADDR_MISALIGNED:  next_mtval = exception_target_addr.alu_addr;
                EXC_STORE_ADDR_MISALIGNED: next_mtval = exception_target_addr.alu_addr;
                EXC_BREAKPOINT:            next_mtval = current_core_pc;
                EXC_ECALL_M:               next_mtval = 32'd0;
                default:                   next_mtval = mtval;
            endcase
        end
        else if (write_enable & (address == CSR_MTVAL)) begin
            next_mtval = write_back_to_csr;
        end
    end

    // Next-state logic for the flush-cache CSR.
    always_comb begin
        // Self-clear: once the flag has pulsed, drop it back to 0 the next cycle so
        // the cache only ever sees a single-cycle flush request.
        if (flush_cache_flag) begin
            next_flush_cache = 32'd0;
        end
        // A CSR write targeting this register: take the func3-computed value.
        else if (write_enable && (address == CSR_FLUSH_CACHE)) begin
            next_flush_cache = write_back_to_csr;
        end
        else begin
            next_flush_cache = flush_cache;
        end
    end

    // logic for the cachable base and limit CSR
    always_comb begin
        next_non_cachable_base = non_cachable_base;
        if (write_enable & (address == CSR_NON_CACHABLE_BASE)) begin
            next_non_cachable_base = write_back_to_csr;
        end

        next_non_cachable_limit = non_cachable_limit;
        if (write_enable & (address == CSR_NON_CACHABLE_LIMIT)) begin
            next_non_cachable_limit = write_back_to_csr;
        end
    end

    // Read mux: drive read_data with the addressed CSR, or 0 if the address is unmapped.
    always_comb begin
        case (address)
            CSR_FLUSH_CACHE: read_data = flush_cache;
            CSR_NON_CACHABLE_BASE: read_data = non_cachable_base;
            CSR_NON_CACHABLE_LIMIT: read_data = non_cachable_limit;

            CSR_MSTATUS: read_data = mstatus;
            CSR_MIE:     read_data = mie;
            CSR_MIP:     read_data = mip;
            CSR_MTVEC:   read_data = mtvec;
            CSR_MEPC:    read_data = mepc;
            CSR_MCAUSE:  read_data = mcause;
            CSR_MTVAL:   read_data = mtval;

            default: read_data = 32'd0;
        endcase
    end

    logic [31:0] or_result;
    logic [31:0] nand_result;

    always_comb begin
        or_result   = write_data | read_data;    // CSRRS: set the bits high in write_data
        nand_result = read_data & (~write_data);  // CSRRC: clear the bits set in write_data
    end

    // Pick the candidate that matches the instruction's func3 (low bits select op,
    // high bit only distinguishes register vs immediate forms, same op either way).
    always_comb begin
        case (func3)
            3'b001, 3'b101: write_back_to_csr = write_data;   // CSRRW: overwrite

            3'b010, 3'b110: write_back_to_csr = or_result;    // CSRRS: set bits

            3'b011, 3'b111: write_back_to_csr = nand_result;  // CSRRC: clear bits

            default: write_back_to_csr = 32'd0;               // func3 000/100: no CSR op
        endcase
    end

    // Output CSR signals assignment
    // Bit 0 of the flush CSR is the flush request line into the cache.
    assign flush_cache_flag = flush_cache[0];
    assign non_cachable_base_address = non_cachable_base;
    assign non_cachable_limit_address = non_cachable_limit;

    // Output trap signal assignment
    assign trap = (((|(mie & mip )) && mstatus[3]) || exception) & ~trap_taken;
    
endmodule