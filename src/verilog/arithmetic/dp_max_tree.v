`include "dp_defs.vh"
// Balanced signed MAX with explicit activity. An inactive tree returns zero.
// DP uses this signed compare on integer exponent coordinates (F0).
module dp_max_tree #(
  parameter integer N = 4,
  parameter integer W = 10
) (
  input wire [N*W-1:0] in_values,
  input wire [N-1:0] in_active,
  output wire signed [W-1:0] out_max,
  output wire out_active
);

  generate
    if (N == 1) begin : g_leaf
      assign out_active = in_active[0];
      assign out_max = in_active[0] ? in_values : {W{1'b0}};
    end else begin : g_branch
      localparam integer LEFT  = N / 2;
      localparam integer RIGHT = N - LEFT;
      wire signed [W-1:0] left_max;
      wire signed [W-1:0] right_max;
      wire left_active;
      wire right_active;
      dp_max_tree #(
        .N(LEFT),
        .W(W)
      ) u_left_tree (
        .in_values(in_values[0+:LEFT*W]),
        .in_active(in_active[0+:LEFT]),
        .out_max(left_max),
        .out_active(left_active)
      );
      dp_max_tree #(
        .N(RIGHT),
        .W(W)
      ) u_right_tree (
        .in_values(in_values[LEFT*W+:RIGHT*W]),
        .in_active(in_active[LEFT+:RIGHT]),
        .out_max(right_max),
        .out_active(right_active)
      );
      assign out_active = left_active | right_active;
      assign out_max = left_active & (~right_active | left_max >= right_max) ? left_max : right_max;
    end
  endgenerate
endmodule
