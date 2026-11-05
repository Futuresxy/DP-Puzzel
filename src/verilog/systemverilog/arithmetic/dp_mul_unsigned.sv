// Combinational unsigned multiplier; input isolation belongs to its caller.
// S0I(ia)F(fa) x S0I(ib)F(fb) -> S0I(ia+ib)F(fa+fb).
module dp_mul_unsigned #(parameter integer A_W=8, B_W=8)(
  input wire [A_W-1:0] in_a, input wire [B_W-1:0] in_b,
  output wire [A_W+B_W-1:0] out_product
);
  assign out_product=in_a*in_b;
endmodule
