// reader.sv
//
// Load-side mirror of byte_enable_decoder. The decoder PLACES a byte/half into
// memory with   (reg_read & 32'h000000FF) << shift .
// The reader does the inverse: it EXTRACTS the byte/half back down to bit 0 with
//   (mem_data >> shift) & 32'h000000FF , then sign- or zero-extends it.

module reader import cpu_core_pkg::*; (
    input  logic [31:0] mem_data,
    input  logic [3:0] byte_enable,
    input  logic [2:0] func3,

    output logic [31:0] write_back_data,
    output logic valid
);

    logic is_signed;
    assign is_signed = ~func3[2]; //is the value signed or unsigned?

    logic [31:0] raw_data; //selected byte/half shifted down to bit 0, upper bits masked to 0

    always_comb begin
        raw_data = 32'b0;
        write_back_data = 32'b0;
        // the decoder already zeroes byte_enable for misaligned accesses,
        // so a non-zero mask is exactly what makes a load valid
        valid = |byte_enable;

        case (func3)
            //LB, LBU --> load one byte. Mask keeps only the bottom byte after the shift.
            FUNC3_BYTE, FUNC3_BYTE_U: begin
                case (byte_enable)
                    4'b0001: raw_data = (mem_data) & 32'h000000FF; //no shift
                    4'b0010: raw_data = (mem_data >> 8)  & 32'h000000FF; //one byte
                    4'b0100: raw_data = (mem_data >> 16) & 32'h000000FF; //2 bytes
                    4'b1000: raw_data = (mem_data >> 24) & 32'h000000FF; //3 bytes
                    default: raw_data = 32'b0;
                endcase
                //signed (lb): replicate bit 7. unsigned (lbu): mask already zero-extended.
                write_back_data = is_signed ? {{24{raw_data[7]}}, raw_data[7:0]} : raw_data;
            end

            //LH, LHU --> load two bytes. Mask keeps the bottom half word after the shift.
            FUNC3_HALFWORD, FUNC3_HALFWORD_U: begin
                case (byte_enable)
                    4'b0011: raw_data = (mem_data) & 32'h0000FFFF; //no shift
                    4'b1100: raw_data = (mem_data >> 16) & 32'h0000FFFF; //shift 16 bits
                    default: raw_data = 32'b0;
                endcase
                //signed (lh): replicate bit 15. unsigned (lhu): mask already zero-extended.
                write_back_data = is_signed ? {{16{raw_data[15]}}, raw_data[15:0]} : raw_data;
            end

            //LW --> full word, no shifting or extending needed
            FUNC3_WORD: write_back_data = mem_data;

            default: write_back_data = 32'b0;
        endcase
    end

endmodule
