module csrfile import cpu_core_pkg::*; (
    input logic clk,
    input logic rst_n,
    input logic [2:0] func3,        // CSR op: write / set / clear (csrrw / csrrs / csrrc)
    input logic [31:0] write_data,  // value coming from the source register (rs1)
    input logic write_enable,
    input logic [11:0] address,     // CSR address from the instruction immediate

    output logic [31:0] read_data,  // current value of the addressed CSR (0 if unmapped)

    //CSR flags
    output logic flush_cache_flag,   // 1-cycle pulse telling the cache to flush
    output logic [31:0] non_cachable_base_address, //base address for non cachable range
    output logic [31:0] non_cachable_limit_address //limit address for non cachable range
);

    logic [31:0] flush_cache, next_flush_cache;
    logic [31:0] non_cachable_base, next_non_cachable_base;
    logic [31:0] non_cachable_limit, next_non_cachable_limit;
    logic [31:0] write_back_to_csr; // value the addressed CSR would take

    always_ff @(posedge clk) begin
        if (~rst_n) begin
            flush_cache <= 32'd0; 
            non_cachable_base <= 32'd0;
            non_cachable_limit <= 32'd0;
        end
        else begin
            flush_cache <= next_flush_cache;
            non_cachable_base <= next_non_cachable_base;
            non_cachable_limit <= next_non_cachable_limit;
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

    //logic for the cachable base and limit CSR
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

    //Output CSR signals assignment
    // Bit 0 of the flush CSR is the flush request line into the cache.
    assign flush_cache_flag = flush_cache[0];
    assign non_cachable_base_address = non_cachable_base;
    assign non_cachable_limit_address = non_cachable_limit;
    
endmodule