module byte_enable_decoder (
    input logic [31:0] alu_result_address,
    input logic [2:0] func3,
    input logic [31:0] reg_read,
    output logic [3:0] byte_enable,
    output logic [31:0] data
);

logic [1:0] offset;

assign offset = alu_result_address[1:0];

always_comb begin
    case (func3)
        //SB. only writes the last byte of register(reg_read)
        //32'h0000000FF acts as bit mask. Same as 0000...0000 1111 1111. 
        //Forces only last byte to be shifted in
        3'b000: begin 
            case (offset)
                2'b00: begin
                    byte_enable = 4'b0001;
                    data = (reg_read & 32'h000000FF); //no shift
                end
                2'b01: begin
                    byte_enable = 4'b0010;
                    data = (reg_read & 32'h000000FF) << 8; //one byte shift
                end
                2'b10: begin
                    byte_enable = 4'b0100;
                    data = (reg_read & 32'h000000FF) << 16; //2 bytes shift
                end
                2'b11: begin
                    byte_enable = 4'b1000;
                    data = (reg_read & 32'h000000FF) << 24; //3 bytes shift
                end
                default: byte_enable = 4'b0000;
            endcase
        end

        3'b001: begin 
            //SH --> store half word
            //Now bit mask masks bottom 16 bits instead of 8 since sh == store half word(16 bits)
            case (offset) 
                2'b00: begin
                    byte_enable = 4'b0011;
                    data = (reg_read & 32'h0000FFFF); 
                end
                2'b10: begin
                    byte_enable = 4'b1100;
                    data = (reg_read & 32'h0000FFFF) << 16; //shift 16 bits
                end
                default: byte_enable = 4'b0000;
            endcase
        end

        3'b010: begin //SW
            byte_enable = (offset == 2'b00) ? 4'b1111: 4'b0000;
            data = reg_read;
        end

        default: byte_enable = 4'b0000; 
    endcase
end

endmodule