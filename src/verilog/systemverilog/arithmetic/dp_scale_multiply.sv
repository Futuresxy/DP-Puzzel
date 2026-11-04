// Shared S5 signed15 x positive-signed9 scale multiplier, with parameter-derived
// physical widths. Both NVFP4 and HiF4 use the same extraction, no compact mux.
module dp_scale_multiply #(
  parameter integer SOP_W=dp_pkg::SCALE_SOP_W,
  parameter integer COEFF_W=2*dp_pkg::SCALE_M+1
)(
  input wire signed [SOP_W-1:0] in_sop,
  input wire signed [COEFF_W-1:0] in_coefficient,
  output wire signed [SOP_W+COEFF_W-1:0] out_product
);
  assign out_product=in_sop*in_coefficient;
endmodule
