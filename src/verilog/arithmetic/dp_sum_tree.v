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

  // [完整组合树] 输入第 k 项位于 [k*W+:W]，每项都是含符号的 W 位补码。
  // N>=1、W>=1。每层相邻两项先符号扩展到 W+1 再相加；无需时钟/使能。
  // 调用者决定在哪一级 DFF 保存输出；同一个模块用于 pair、lane、group 和 top。
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
          // 奇数最后一项只符号扩展带入下一层，不能丢掉或零扩展负数。
          // 递归每次将项数降到 ceil(N/2)，因此是平衡树，不是 N 项串行加法。
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
