module cache import cpu_core_pkg::*; #(
    parameter CACHE_SIZE = 128
)(
    //CPU Logic Clock and Reset
    input logic clk,
    input logic rst_n,
    input logic aclk, //AXI clock. the same as clk to simplify timing issues

    //CPU connections
    input logic [31:0] address,
    input logic [31:0] write_data,
    input logic read_enable,
    input logic write_enable,
    input logic [3:0] byte_enable,
    input logic csr_flush_order, //CSR can order a manual write-back of the line
    output logic [31:0] read_data,
    output logic cache_stall,

    axi_interface.master axi, //AXI interface

    //state info for the arbitrer
    output cache_state_type cache_state,

    //debug signals
    output logic [6:0] set_ptr_out,
    output logic [6:0] next_set_ptr_out
);

    assign set_ptr_out = set_ptr;
    assign next_set_ptr_out = next_set_ptr;

    //How each cache line is organized:
    // DIRTY | VALID | BLOCK TAG | INDEX/SET | OFFSET | DATA

    logic [CACHE_SIZE-1:0][31:0] cache_data;
    logic [31:9] cache_block_tag;
    logic is_cache_valid;
    logic is_next_cache_valid;
    logic is_cache_dirty;
    logic is_next_cache_dirty;
    //remember why we are writing back: a miss eviction or a CSR flush order
    logic csr_flushing;
    logic next_csr_flushing;

    //incoming cache reqest signals
    logic [31:9] request_block_tag;
    assign request_block_tag = address[31:9];
    logic [8:2] request_index;
    assign request_index = address[8:2];

    logic [31:0] byte_enable_mask; //Only want to write specific bytes on a WORD based on byte_enable
    assign byte_enable_mask = {
        {8{byte_enable[3]}},
        {8{byte_enable[2]}},
        {8{byte_enable[1]}},
        {8{byte_enable[0]}}
    };

    //Hit logic
    logic hit;

    //valid, and the requested tag matches the caches actual tag
    assign hit = (request_block_tag == cache_block_tag) && is_cache_valid;

    //Stall logic: stall while a transaction is in flight, or on a fresh miss
    logic comb_stall, seq_stall;
    assign comb_stall = (next_state != IDLE) | (~hit & (read_enable | actual_write_enable));
    assign cache_stall = comb_stall | seq_stall;

    //Cache Logic --> FSM
    cache_state_type state, next_state;

    always_ff @(posedge clk) begin //We actually write or refresh the cache here
        if (~rst_n) begin
            is_cache_valid <= 1'b0;
            is_cache_dirty <= 1'b0;
            seq_stall <= 1'b0;
            csr_flushing <= 1'b0;
        end
        else begin
            is_cache_valid <= is_next_cache_valid;
            is_cache_dirty <= is_next_cache_dirty;
            seq_stall <= comb_stall;
            csr_flushing <= next_csr_flushing;

            if (hit & write_enable & state == IDLE) begin //Begin a write to the cache
                cache_data[request_index] <=
                    (cache_data[request_index] & ~byte_enable_mask) | //preserve the old data
                    (write_data & byte_enable_mask); //combine with the new data
                is_cache_dirty <= 1'b1; //just modified the cache, so its now dirty
            end

            //refill from memory: a beat transfers only when rvalid & rready are both high
            else if (axi.rvalid & state == RECIEVING_READ_DATA & axi.rready) begin
                //capture this beat into the line; set_ptr advances per beat across the burst
                cache_data[set_ptr] <= axi.rdata;
                if (axi.rready & axi.rlast) begin //rlast marks the final beat: line is now fully loaded
                    cache_block_tag <= request_block_tag; //stamp the tag so future lookups hit
                    is_cache_dirty <= 1'b0; //loaded straight from memory, so the line is clean
                end
            end
        end
    end

    logic [6:0] set_ptr;
    logic [6:0] next_set_ptr;

    logic actual_write_enable;
    assign actual_write_enable = write_enable & |byte_enable;

    always_ff @(posedge aclk) begin //AXI clock driven seq logic
        if (~rst_n) begin
            state <= IDLE;
            set_ptr <= 7'b0;
        end
        else begin
            state <= next_state;
            set_ptr <= next_set_ptr;
        end
    end

    //FSM to determine each stage of FSM, different cases
    always_comb begin
        //defaults
        next_state = state;
        is_next_cache_valid = is_cache_valid;
        is_next_cache_dirty = is_cache_dirty;
        next_csr_flushing = csr_flushing; //hold the flush flag by default
        axi.wlast = 1'b0;

        axi.wdata = cache_data[set_ptr];
        cache_state = state;
        next_set_ptr = set_ptr;

        case (state)
            IDLE: begin
                //can't do both at once
                if (read_enable && write_enable) $display("ERROR, CAN'T READ AND WRITE AT THE SAME TIME!!!");

                //we successfully read
                else if (hit && read_enable) read_data = cache_data[request_index];

                //CSR ordered a flush: force a write-back and skip the read-back afterwards
                else if (csr_flush_order) begin
                    next_csr_flushing = 1'b1;
                    next_state = SENDING_WRITE_REQUEST;
                end

                //we missed and we tried to either read or write to cache
                else if (~hit && (read_enable | actual_write_enable)) begin
                    //if dirty, we have to write
                    next_state = (is_cache_dirty) ? SENDING_WRITE_REQUEST : SENDING_READ_REQUEST;
                end

                // IDLE AXI SIGNALS : no request
                // No write
                axi.awvalid = 1'b0;
                axi.wvalid = 1'b0;
                axi.bready = 1'b0;
                // No read
                axi.arvalid = 1'b0;
                axi.rready = 1'b0;

                // Defaults to 0
                next_set_ptr = 7'b0;
            end

            SENDING_WRITE_REQUEST: begin
                // HANDLE MISS WITH DIRTY CACHE : write the CURRENT line back to memory first
                axi.awaddr = {cache_block_tag, 7'b0000000, 2'b00}; // tag, set, offset

                if (axi.awready) next_state = SENDING_WRITE_DATA;

                // SENDING_WRITE_REQUEST AXI SIGNALS : address request
                // Write address is okay
                axi.awvalid = 1'b1;
                axi.wvalid = 1'b0;
                axi.bready = 1'b0;
                // No read
                axi.arvalid = 1'b0;
                axi.rready = 1'b0;
            end

            SENDING_WRITE_DATA: begin
                if (axi.wready) next_set_ptr = set_ptr + 1;

                if (set_ptr == 7'd127) begin
                    axi.wlast = 1'b1;
                    if (axi.wready) next_state = WAITING_WRITE_RECIEVE;
                end

                // SENDING_WRITE_DATA AXI SIGNALS : sending data
                // Write stuff
                axi.awvalid = 1'b0;
                axi.wvalid = 1'b1;
                axi.bready = 1'b0;
                // No read
                axi.arvalid = 1'b0;
                axi.rready = 1'b0;
            end

            WAITING_WRITE_RECIEVE: begin
                if (axi.bvalid && (axi.bresp == 2'b00)) begin //response is OKAY
                    if (csr_flushing) begin
                        //the write-back was a CSR flush: clear the flag and go back to idle
                        next_state = IDLE;
                        next_csr_flushing = 1'b0;
                    end
                    else begin
                        //the write-back was a miss eviction: now fetch the new line
                        next_state = SENDING_READ_REQUEST;
                    end
                end
                else if (axi.bvalid && (axi.bresp != 2'b00)) begin
                    $display("ERROR WRITING TO MAIN MEMORY !");
                end

                // WAITING_WRITE_RECIEVE AXI SIGNALS : ready for the response
                // No write
                axi.awvalid = 1'b0;
                axi.wvalid = 1'b0;
                axi.bready = 1'b1;
                // No read
                axi.arvalid = 1'b0;
                axi.rready = 1'b0;
            end

            SENDING_READ_REQUEST : begin
                // HANDLE MISS : Read
                axi.araddr = {request_block_tag, 7'b0000000, 2'b00}; // tag, set, offset

                if(axi.arready) begin
                    next_state = RECIEVING_READ_DATA;
                end

                // SENDING_READ_REQ AXI SIGNALS : address request
                // No write
                axi.awvalid = 1'b0;
                axi.wvalid = 1'b0;
                axi.bready = 1'b0;
                // No read but address is okay
                axi.arvalid = 1'b1;
                axi.rready = 1'b0;
            end

            RECIEVING_READ_DATA: begin

                if (axi.rvalid) begin
                    // Increment pointer on valid data
                    next_set_ptr = set_ptr + 1;

                    if (axi.rlast) begin
                        // Transition to IDLE on the last beat
                        next_state = IDLE;
                        is_next_cache_valid = 1'b1;
                    end
                end

                // AXI Signals
                axi.awvalid = 1'b0;
                axi.wvalid = 1'b0;
                axi.bready = 1'b0;
                axi.arvalid = 1'b0;
                axi.rready = 1'b1;
            end

            default : begin
                $display("CACHE FSM SATETE ERROR");
            end
        endcase
    end

    // ADDRESS CHANNELS
    // -----------------
    // WRITE Burst sizes are fixed type & len
    assign axi.awlen = CACHE_SIZE-1; // full cache reloaded each time
    assign axi.awsize = 3'b010; // 2^<awsize> = 2^2 = 4 Bytes
    assign axi.awburst = 2'b01; // INCREMENT
    // READ Burst sizes are fixed type & len
    assign axi.arlen = CACHE_SIZE-1; // full cache reloaded each time
    assign axi.arsize = 3'b010; // 2^<arsize> = 2^2 = 4 Bytes
    assign axi.arburst = 2'b01; // INCREMENT
    // W/R ids are always 0 
    assign axi.awid = 4'b0000;
    assign axi.arid = 4'b0000;

    // DATA CHANNELS
    // -----------------
    // Write data
    assign axi.wstrb = 4'b1111; // We handle data masking in cache itself

endmodule
