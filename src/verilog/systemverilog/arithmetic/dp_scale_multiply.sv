// S5 unsigned scale multiply. A=magnitude, B=scale pair, Y=product.
// Precision | A S | A I | A F | B S | B I | B F | Y S | Y I | Y F
// --------- | --- | --- | --- | --- | --- | --- | --- | --- | ---
// NVFP4     | 0   | 10  | 4   | 0   | 2   | 6   | 0   | 12  | 10
// HiF4      | 0   | 8   | 6   | 0   | 2   | 6   | 0   | 10  | 12
// Sign travels separately.
module dp_scale_multiply #(
  parameter integer MAG_W=dp_pkg::SCALE_SOP_W-1,
  parameter integer COEFF_W=2*dp_pkg::SCALE_M
)(
  input wire [MAG_W-1:0] in_magnitude,
  input wire [COEFF_W-1:0] in_coefficient,
  output wire [MAG_W+COEFF_W-1:0] out_product
);

  assign out_product=in_magnitude*in_coefficient;
endmodule
