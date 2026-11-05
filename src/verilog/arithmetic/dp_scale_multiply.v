`include "dp_defs.vh"
// Shared S5 unsigned magnitude multiply. NVFP4 S0I10F4 or HiF4 S0I8F6
// times S0I2F6 yields S0I12F10 or S0I10F12. Sign travels separately.
module dp_scale_multiply #(
  parameter integer MAG_W   = `DP_SCALE_SOP_W - 1,
  parameter integer COEFF_W = 2 * `DP_SCALE_M
) (
  input wire [MAG_W-1:0] in_magnitude,
  input wire [COEFF_W-1:0] in_coefficient,
  output wire [MAG_W+COEFF_W-1:0] out_product
);

  assign out_product = in_magnitude * in_coefficient;
endmodule
