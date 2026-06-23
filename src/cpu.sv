`timescale 1ns/1ps

module cpu import cpu_core_pkg::*; (
    input logic clk,
    input logic rst_n,
    // Single external memory bus. The instruction and data caches each master
    // their own AXI interface; the arbiter merges them onto this one port.
    axi_interface.master m_axi
);

    //Program counter(pc)
    logic [31:0] pc;
    logic [31:0] pc_next;
    logic [31:0] pc_target;
    logic [31:0] pc_plus_four;

    assign pc_plus_four = pc + 4;

    always_comb begin
        case(pc_source)
            PC_PLUS_4:     pc_next = pc_plus_four;
            PC_TARGET:     pc_next = pc_target; //a jump
            PC_ALU_RESULT: pc_next = alu_result; //jalr
            default:       pc_next = pc_plus_four;
        endcase
    end

    always_comb begin
        case(second_add_source) 
            1'b0: pc_target = pc + immediate;
            1'b1: pc_target = immediate;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst_n == 0) begin
            pc <= 32'b0;
        end else if (~global_stall) begin
            //freeze the PC while either cache is busy (miss / write-back in flight)
            pc <= pc_next;
        end
    end

    //Global stall: high whenever the instruction or data cache cannot complete
    //its access this cycle. It freezes the PC and squashes the register write so
    //the same instruction is retried until both caches are ready.
    logic i_cache_stall;
    logic d_cache_stall;
    logic global_stall;
    assign global_stall = i_cache_stall | d_cache_stall;

    //Instruction word fetched from the instruction cache (driven by instruction_cache below)
    logic [31:0] instruction;

    //Control
    //Generate control signals from instruction data in control unit
    logic [6:0] op; //opcode
    assign op = instruction[6:0];
    logic [2:0] func3; //function 3

    assign func3 = instruction[14:12];
    logic [6:0] func7;
    assign func7 = instruction[31:25];

    logic alu_zero;
    logic alu_last;
    //out of control
    alu_control_type alu_control;
    imm_source_type imm_source;
    logic mem_write;
    logic reg_write;
    //out muxes
    logic alu_source;
    write_back_source_type write_back_source;

    pc_source_type pc_source;
    logic second_add_source;

    logic mem_read_enable;

    logic csr_write_back_source; //selects rs1 value vs zimm as the CSR write data
    logic csr_write_enable;      //this instruction writes a CSR

    control control(
        .op(op),
        .func3(func3),
        .func7(func7),
        .alu_zero(alu_zero),
        .alu_last(alu_last),
        //Out
        .alu_control(alu_control),
        .imm_source(imm_source),
        .mem_write(mem_write),
        .mem_read(mem_read_enable),
        .reg_write(reg_write),
        //Muxes out
        .alu_source(alu_source),
        .write_back_source(write_back_source),

        .pc_source(pc_source),
        .second_add_source(second_add_source),
        //CSR control
        .csr_write_back_source(csr_write_back_source),
        .csr_write_enable(csr_write_enable)
    );

    //Register file

    logic [4:0] source_reg1;
    assign source_reg1 = instruction[19:15];
    logic [4:0] source_reg2;
    assign source_reg2 = instruction[24:20];
    logic [4:0] destination;
    assign destination = instruction[11:7];
    logic [31:0] read_reg1;
    logic [31:0] read_reg2;

    //Pick the value (and its validity) written back to the destination register.
    logic wb_valid;
    logic [31:0] write_back_data;
    always_comb begin
        case (write_back_source)
            //ALU result -> R-type ops (add, and, slt...) and I-type ALU ops (addi, ori...)
            WB_ALU_RESULT: begin
                write_back_data = alu_result;
                wb_valid = 1'b1;
            end
            //Loaded data -> loads (lw/lb/lh/lbu/lhu); wb_valid drops if the load is misaligned
            WB_MEM_READ: begin
                write_back_data = load_data;
                wb_valid = load_valid;
            end
            //Return address pc+4 -> jal and jalr write the link register (rd <= pc + 4)
            WB_PC_PLUS_4: begin
                write_back_data = pc_plus_four;
                wb_valid = 1'b1;
            end
            //Second-adder output -> auipc (rd <= pc + imm) and lui (rd <= imm)
            WB_SECOND_ADD: begin
                write_back_data = pc_target;
                wb_valid = 1'b1;
            end
            //CSR read value -> csr* instructions write the OLD csr value into rd
            WB_CSR_READ: begin
                write_back_data = csr_read_data;
                wb_valid = 1'b1;
            end
            default: begin
                write_back_data = alu_result;
                wb_valid = 1'b1;
            end
        endcase
    end

    regfile regfile(
        .clk(clk),
        .rst_n(rst_n),
        //Read In
        .address1(source_reg1),
        .address2(source_reg2),
        //Read Out
        .read_data1(read_reg1),
        .read_data2(read_reg2),
        //Write In
        //stop the write if the load is invalid (misaligned) or while stalled (data not ready yet)
        .write_enable(reg_write & wb_valid & ~global_stall),
        .write_data(write_back_data),
        .address3(destination)
    );

    //Sign extend
    //Pulls immediate out of instruction and stretches to 32 bit fo alu
    logic [24:0] raw_immediate;
    assign raw_immediate = instruction[31:7]; //lower bits are the opcode
    logic [31:0] immediate;

    signext sign_extender (
        .raw_src(raw_immediate),
        .imm_source(imm_source),
        .immediate(immediate)
    );

    logic [31:0] alu_result;
    logic [31:0] alu_source2;

    always_comb begin
        case (alu_source)
            1'b1: alu_source2 = immediate;
            default: alu_source2 = read_reg2;
        endcase
    end

    alu alu(
        .alu_control(alu_control),
        .src1(read_reg1),
        .src2(alu_source2),
        .alu_result(alu_result),
        .zero(alu_zero),
        .alu_last(alu_last)
    );

    //CSR file
    //Holds the few implemented CSRs and emits their control flags (e.g. cache flush).
    logic [11:0] csr_address;
    assign csr_address = instruction[31:20]; //CSR address field of the instruction
    logic [31:0] csr_read_data;  //old CSR value, routed to the write-back mux
    logic [31:0] csr_write_data; //value written into the CSR (rs1 or zimm)
    logic flush_cache_flag;      //one-cycle pulse ordering the data cache to flush

    //Pick the CSR write source: register form uses rs1, immediate form uses the
    //zero-extended zimm (signext already produces it as `immediate` for CSR ops).
    always_comb begin
        case (csr_write_back_source)
            1'b0: csr_write_data = read_reg1;  //csrrw / csrrs / csrrc
            1'b1: csr_write_data = immediate;  //csrrwi / csrrsi / csrrci
        endcase
    end

    csrfile csr_file (
        .clk(clk),
        .rst_n(rst_n),
        .func3(func3),
        .write_data(csr_write_data),
        //only commit the CSR write when the instruction retires (not while stalled)
        .write_enable(csr_write_enable & ~global_stall),
        .address(csr_address),
        .read_data(csr_read_data),
        .flush_cache_flag(flush_cache_flag)
    );

    //Load/Store Unit
    //Wraps the store-side byte_enable_decoder and the load-side reader. It sits
    //around the data memory: it produces the aligned write data + byte_enable on
    //the store path, and turns the raw word read back into the value written to a
    //register on the load path.
    logic [3:0]  mem_byte_enable; //write mask + load-lane select (LSU -> memory & reader)
    logic [31:0] mem_write_data;  //store data, aligned into its lane (LSU -> memory)
    logic [31:0] mem_read;        //raw word read back from memory (memory -> LSU)
    logic [31:0] load_data;       //the processed load result, fed to the write-back mux
    logic load_valid;             //low when the load is misaligned -> write-back is squashed

    load_store_unit lsu (
        .alu_result_address(alu_result),
        .reg_read(read_reg2),
        .func3(func3),
        .mem_data(mem_read),
        .byte_enable(mem_byte_enable),
        .write_data(mem_write_data),
        .load_data(load_data),
        .load_valid(load_valid)
    );

    //Caches + AXI arbiter
    //Each cache masters its own AXI interface; the arbiter merges the two onto
    //the single external m_axi bus, granting the instruction cache priority.
    axi_interface i_cache_axi(); //instruction cache <-> arbiter
    axi_interface d_cache_axi(); //data cache <-> arbiter

    cache_state_type i_cache_state; //drives arbitration: non-IDLE means "I want the bus"
    cache_state_type d_cache_state;

    //Instruction cache: read-only, always fetching the word at the PC.
    cache instruction_cache (
        .clk(clk),
        .rst_n(rst_n),
        .aclk(clk), //AXI clock tied to the CPU clock to keep timing simple

        //CPU connection
        .address(pc),
        .write_data(32'd0),
        .read_enable(1'b1),
        .write_enable(1'b0),
        .byte_enable(4'd0),
        .csr_flush_order(1'b0), //never flushed by a CSR
        .read_data(instruction),
        .cache_stall(i_cache_stall),

        //AXI request connection (to the arbiter)
        .axi(i_cache_axi.master),
        .cache_state(i_cache_state),

        //debug taps (unused at the core level)
        .set_ptr_out(),
        .next_set_ptr_out()
    );

    //Data cache: serves loads and stores from the datapath / LSU.
    cache data_cache (
        .clk(clk),
        .rst_n(rst_n),
        .aclk(clk),

        //CPU connection
        .address(alu_result),
        .write_data(mem_write_data),
        .read_enable(mem_read_enable),
        .write_enable(mem_write),
        .byte_enable(mem_byte_enable),
        .csr_flush_order(flush_cache_flag), //CSR-ordered manual write-back
        .read_data(mem_read),
        .cache_stall(d_cache_stall),

        //AXI request connection (to the arbiter)
        .axi(d_cache_axi.master),
        .cache_state(d_cache_state),

        //debug taps (unused at the core level)
        .set_ptr_out(),
        .next_set_ptr_out()
    );

    //Arbiter: muxes the two cache interfaces onto the single external bus.
    cache_arbiter arbiter (
        .m_axi(m_axi),
        .s_axi_instruction(i_cache_axi.slave),
        .i_cache_state(i_cache_state),
        .s_axi_data(d_cache_axi.slave),
        .d_cache_state(d_cache_state)
    );

endmodule