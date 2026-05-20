module cpu(
    input logic clk,
    input logic rst_n
);

//Counter
logic [31:0] pc;
logic [31:0] pc_next;

always_comb begin
    pc_next = pc + 4;
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
    .rst_n(1'b1),
    .read_data(instruction) //output
);

//Control

//Generate control signals from instruction data in control unit
logic [6:0] op; //opcode
assign op = instruction[6:0];
logic [2:0] func3; //function 3
assign func3 = instruction[14:12];
logic alu_zero;
//out of control
logic [2:0] alu_control;
logic [1:0] imm_source;
logic mem_write;
logic reg_write;
//out muxes
logic alu_source;
logic write_back_source;

control control(
    .op(op),
    .func3(func3),
    .func7(7'b0),
    .alu_zero(alu_zero),
    //Out
    .alu_control(alu_control),
    .imm_source(imm_source),
    .mem_write(mem_write),
    .reg_write(reg_write),
    //Muxes out
    .alu_source(alu_source),
    .write_back_source(write_back_source)
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


logic [31:0] write_back_data;
always_comb begin
    case (write_back_source) 
        1'b1: write_back_data = mem_read;
        default: write_back_data = alu_result;
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
    .write_enable(reg_write),
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
    .zero(alu_zero)
);

//Data Memory
logic [31:0] mem_read;

memory #(
    .mem_init("./test_dmemory.hex")
) data_memory (
    //Inputs
    .clk(clk),
    .address(alu_result),
    .write_data(read_reg2),
    .write_enable(mem_write),
    .rst_n(1'b1),
    //Output
    .read_data(mem_read)
);

endmodule