`include "dp_defs.vh"
// Nonnegative scale -> common E8M3. Special encodings remain explicit.
// E8M0/E4M3/E6M2 and unit-scale output S0I1F3 plus separate biased exponent.
module dp_scale_unpack(
  input wire [`DP_SCALE_W-1:0] in_data,
  input wire [`DP_SCALE_TYPE_W-1:0] in_datatype,
  output reg [`DP_SCALE_M-1:0] out_magnitude,
  output reg [`DP_EXP_W-1:0] out_exponent,
  output reg out_nan
);

  `include "dp_functions.vh"
  localparam integer NV_E=4, NV_F=3, NV_BIAS=7, HIF_F=2;
  reg [31:0] exponent_work;
  always @* begin
    out_magnitude=(1<<`DP_SCALE_F); exponent_work=(`DP_SCALE_BIAS); out_nan=0;
    case(in_datatype)
      `DP_SC_E8M0: begin exponent_work={{(32-`DP_SCALE_W){1'b0}},in_data}; out_nan=&in_data; end
      `DP_SC_E6M2: begin
        exponent_work=(({{(32-`DP_SCALE_W){1'b0}},in_data}>>HIF_F)+`DP_SCALE_BIAS-`DP_HIF_SCALE_BIAS);
        out_magnitude={1'b1,in_data[HIF_F-1:0],1'b0}; out_nan=&in_data;
      end
      `DP_SC_E4M3: begin
        exponent_work=((in_data[NV_F+:NV_E]==0 ? 1 : {{(32-NV_E){1'b0}},in_data[NV_F+:NV_E]})+`DP_SCALE_BIAS-NV_BIAS);
        out_magnitude={|in_data[NV_F+:NV_E],in_data[NV_F-1:0]};
        out_nan=&in_data[NV_E+NV_F-1:0];
      end
      default: begin end
    endcase
    out_exponent=exponent_work[`DP_EXP_W-1:0];
    if(out_nan) out_magnitude=0;
  end
endmodule
