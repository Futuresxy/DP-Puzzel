`include "dp_defs.vh"
// E lane S4 的完整坐标融合单元：signed lane sum -> 宽 signed group leaf。
// 纯组合，无时钟、握手或寄存器；group 的 S4 DFF 捕获两个 lane 的合并结果。
// 合法 in_shift=0..DP_E_GUARD(2)，OUT_W>=IN_W+DP_E_GUARD，保证左移无溢出。
// HiF4 的 e2 已变为 coefficient 中的 2^shift；后级不应再应用同一个 e2。
// MX/NV 固定 shift=2 是 F2 -> F4 的静态补零；不会生成新的有效精度。
// 下表对应默认 IN_W=12/OUT_W=14 的 TC 格式；I 不包含 S，均无舍入/截断。
// Precision    | Input S | I | F | Output S | I | F
// ------------ | ------- | - | - | -------- | - | -
// MXFP4/NVFP4 | 1       | 9 | 2 | 1        | 9 | 4
// HiF4         | 1       | 7 | 4 | 1        | 9 | 4
module dp_lane_e_shift #(
  parameter integer IN_W  = 2 * `DP_MUL_LO + 2 + $clog2(`DP_E_LANES / 2),
  parameter integer OUT_W = IN_W + `DP_E_GUARD
) (
  input wire signed [IN_W-1:0] in_sum,
  input wire [$clog2(`DP_E_GUARD+1)-1:0] in_shift,
  output wire signed [OUT_W-1:0] out_sum
);
  wire signed [OUT_W-1:0] extended_sum;
  // 必须先扩展再移位；若先在 IN_W 位中移位，会丢掉高位再也无法补回。
  // 这是精确的补码乘 2^shift，区别于幅值 RTZ 右移；无需先取绝对值。
  assign extended_sum = {{(OUT_W - IN_W) {in_sum[IN_W-1]}}, in_sum};
  assign out_sum = extended_sum <<< in_shift;
endmodule
