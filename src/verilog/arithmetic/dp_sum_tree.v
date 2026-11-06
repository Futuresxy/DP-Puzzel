`include "dp_defs.vh"
// Balanced signed reduction. Odd final leaves are sign extended, never dropped.
// No registers; natural output growth is ceil(log2(N)). N=1 is a wire.
// TC reduction, W=1+i+f, L=ceil(log2(N)).
// Precision / signal | S | I   | F
// ------------------ | - | --- | -
// Each input         | 1 | i   | f
// Output             | 1 | i+L | f
module dp_sum_tree #(
  parameter integer N = 4,
  parameter integer W = 28
) (
  input wire [N*W-1:0] in_values,
  output wire signed [W+$clog2(N)-1:0] out_sum
);
  genvar pair_index;

  generate
    if (N == 1) begin : g_leaf
      assign out_sum = $signed(in_values);
    end else begin : g_level
      localparam integer NEXT_N = (N + 1) / 2;
      wire [NEXT_N*(W+1)-1:0] next_values;
      for (pair_index = 0; pair_index < NEXT_N; pair_index = pair_index + 1) begin : g_pair
        wire signed [W-1:0] pair_left;
        assign pair_left = in_values[(2*pair_index)*W+:W];
        if (2 * pair_index + 1 < N) begin : g_two
          wire signed [W-1:0] pair_right;
          assign pair_right = in_values[(2*pair_index+1)*W+:W];
          assign next_values[pair_index*(W+1)+:W+1] = $signed(
            {pair_left[W-1], pair_left}
          ) + $signed(
            {pair_right[W-1], pair_right}
          );
        end else begin : g_odd
          assign next_values[pair_index*(W+1)+:W+1] = {pair_left[W-1], pair_left};
        end
      end
      dp_sum_tree #(
        .N(NEXT_N),
        .W(W + 1)
      ) u_next_level (
        .in_values(next_values),
        .out_sum  (out_sum)
      );
    end
  endgenerate
endmodule
