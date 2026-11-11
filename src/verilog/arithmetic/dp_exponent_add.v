// Unsigned exponent addition, retaining the carry. No bias subtraction here.
module dp_exponent_add #(
  parameter integer W = 8
) (
  input  wire [W-1:0] in_a,
  input  wire [W-1:0] in_b,
  output wire [  W:0] out_sum
);
  assign out_sum = {1'b0, in_a} + {1'b0, in_b};
endmodule
