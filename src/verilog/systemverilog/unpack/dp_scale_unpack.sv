// Nonnegative scale -> common E8M3. Special encodings remain explicit.
module dp_scale_unpack(
  input wire [dp_pkg::SCALE_W-1:0] in_data,
  input wire [dp_pkg::SCALE_TYPE_W-1:0] in_datatype,
  output reg [dp_pkg::SCALE_M-1:0] out_magnitude,
  output reg [dp_pkg::EXP_W-1:0] out_exponent,
  output reg out_nan
);
  import dp_pkg::*;
  localparam integer NV_E=4, NV_F=3, NV_BIAS=7, HIF_F=2;
  always_comb begin
    out_magnitude=SCALE_M'(1<<SCALE_F); out_exponent=EXP_W'(SCALE_BIAS); out_nan=0;
    case(in_datatype)
      SC_E8M0: begin out_exponent=in_data; out_nan=&in_data; end
      SC_E6M2: begin
        out_exponent=EXP_W'((int'(in_data)>>HIF_F)+SCALE_BIAS-HIF_SCALE_BIAS);
        out_magnitude={1'b1,in_data[HIF_F-1:0],1'b0}; out_nan=&in_data;
      end
      SC_E4M3: begin
        out_exponent=EXP_W'((in_data[NV_F+:NV_E]==0 ? 1 : int'(in_data[NV_F+:NV_E]))+SCALE_BIAS-NV_BIAS);
        out_magnitude={|in_data[NV_F+:NV_E],in_data[NV_F-1:0]};
        out_nan=&in_data[NV_E+NV_F-1:0];
      end
      default: begin end
    endcase
    if(out_nan) out_magnitude='0;
  end
endmodule
