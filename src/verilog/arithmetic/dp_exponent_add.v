// Unsigned exponent addition, retaining the carry. No bias subtraction here.
module dp_exponent_add #(
  parameter integer W = 8
) (
  // verilog_format: off  // Keep ports sharing one declaration on the same line.
  input wire [W-1:0] in_a,in_b,
  output wire [W:0] out_sum
  // verilog_format: on
);
  assign out_sum = {1'b0, in_a} + {1'b0, in_b};
endmodule
