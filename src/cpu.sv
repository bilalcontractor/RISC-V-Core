module cpu import cpu_core_pkg::*; (
    input logic clk,
    input logic rst_n
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
    end else begin
        pc <= pc_next;
    end
end

//Instruction memory

logic [31:0] instruction; 

memory #(
    .mem_init("./test_imemory.hex")
) instruction_memory (
    .clk(clk),
    .address(pc),
    .write_data(32'b0),
    .write_enable(1'b0),
    .byte_enable(mem_byte_enable),
    .rst_n(1'b1),
    .read_data(instruction) //output
);

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
    .reg_write(reg_write),
    //Muxes out
    .alu_source(alu_source),
    .write_back_source(write_back_source),

    .pc_source(pc_source),
    .second_add_source(second_add_source)
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
    .write_enable(reg_write & wb_valid), //squash the write if the load is invalid (misaligned)
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

//Byte Enable Decoder
logic [3:0] mem_byte_enable;
logic [31:0] mem_write_data;

byte_enable_decoder byte_decoder (
    .alu_result_address(alu_result),
    .reg_read(read_reg2),
    .func3(func3),
    .byte_enable(mem_byte_enable),
    .data(mem_write_data)
);

//Data Memory
logic [31:0] mem_read;

memory #(
    .mem_init("./test_dmemory.hex")
) data_memory (
    //Inputs
    .clk(clk),
    .address({alu_result[31:2], 2'b00}),
    .write_data(mem_write_data),
    .write_enable(mem_write),
    .byte_enable(mem_byte_enable),
    .rst_n(1'b1),
    //Output
    .read_data(mem_read)
);

//Reader
//Processes the raw word from data memory into the value loaded into a register:
//selects the byte/half lane (byte_enable), then sign- or zero-extends it (func3).
logic [31:0] load_data;  //the processed load result, fed to the write-back mux
logic load_valid;        //low when the load is misaligned -> write-back is squashed

reader reader(
    .mem_data(mem_read),
    .byte_enable(mem_byte_enable),
    .func3(func3),
    .write_back_data(load_data),
    .valid(load_valid)
);

endmodule