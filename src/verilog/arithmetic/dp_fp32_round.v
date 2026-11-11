`include "dp_defs.vh"
// Finite signed SOP -> FP32, RNE only. One rounding operation after the two
// architected RTZ cuts. Supports subnormals, ties, signed zero and overflow.
// Combinational S8 block; special-result selection is owned by the top.
// S8 finite path.
// Precision / signal | S | I                  | F
// ------------------ | - | ------------------ | --------------
// Input SOP (TC)     | 1 | SUM_W-GLOBAL_MAG_W | GLOBAL_MAG_W-1
// Rounded magnitude  | 0 | 1                  | 23
// Input coordinate is in_anchor. Output FP32 encodes sign/exponent/fraction 1/8/23.
module dp_fp32_round #(
  parameter integer SUM_W = 43,
  parameter integer ANCHOR_W = 10,
  parameter integer GLOBAL_MAG_W = 39
) (
  input wire signed [SUM_W-1:0] in_sum,
  input wire signed [ANCHOR_W-1:0] in_anchor,
  input wire in_negative_zero,
  output wire [`DP_FP32_W-1:0] out_bits
);

  `include "dp_functions.vh"
  localparam integer COUNT_W = $clog2(SUM_W + 1);
  localparam integer ROUND_W = SUM_W + 1;
  // [S8 符号/幅值] 普通负数取 abs；精确零使用 S7 传入的 negative_zero 旁带。
  // SUM_W 包含规约增长位；本模块不处理 NaN/Inf 输入，特殊路径由 top 选择。
  wire sign_value;
  assign sign_value = in_sum[SUM_W-1] | (in_sum == 0 & in_negative_zero);
  wire [SUM_W-1:0] magnitude;
  assign magnitude = in_sum[SUM_W-1] ? -in_sum : in_sum;
  wire [COUNT_W-1:0] leading;
  wire active;
  dp_lzd #(
    .W(SUM_W)
  ) u_output_leading_detect (
    .in_magnitude(magnitude),
    .out_count(leading),
    .out_active(active)
  );
  localparam integer EXP_CALC_W = ANCHOR_W + 1;
  localparam integer WINDOW_OFFSET_INT = GLOBAL_MAG_W - 1;
  localparam signed [EXP_CALC_W-1:0] WINDOW_OFFSET = WINDOW_OFFSET_INT[EXP_CALC_W-1:0];
  localparam signed [EXP_CALC_W-1:0] MIN_EXP = `DP_FP32_MIN_E;
  localparam signed [EXP_CALC_W-1:0] MAX_EXP = `DP_FP32_MAX_E;
  localparam signed [EXP_CALC_W-1:0] BIAS = `DP_FP32_BIAS;
  wire signed [EXP_CALC_W-1:0] exponent_value;
  wire signed [EXP_CALC_W-1:0] lsb_value;
  wire signed [EXP_CALC_W-1:0] exponent_after_carry;
  wire signed [EXP_CALC_W-1:0] biased_exponent;
  wire signed [31:0] shift_value;
  wire signed [31:0] highest_bit_index;
  wire [ROUND_W-1:0] shifted_magnitude;
  wire [ROUND_W-1:0] rounded;
  wire [ROUND_W-1:0] normalized;
  wire [SUM_W-1:0] guard_candidates;
  wire [SUM_W-1:0] sticky_candidates;
  wire round_increment;
  wire normal_result;
  wire [`DP_FP32_W-1:0] finite_bits;
  genvar bit_index;
  // [S8 规格化坐标] LSB 指数=anchor-(GLOBAL_MAG_W-1)，再加最高有效位索引。
  // 正规数对齐到 24 位有效数；非正规数固定对齐到 FP32 的 2^-149 坐标。
  assign highest_bit_index = SUM_W - 1 - {{(32 - COUNT_W) {1'b0}}, leading};
  assign lsb_value = $signed({in_anchor[ANCHOR_W-1], in_anchor}) - WINDOW_OFFSET;
  assign exponent_value = lsb_value + $signed(highest_bit_index[EXP_CALC_W-1:0]);
  assign normal_result = exponent_value >= MIN_EXP;
  assign
    shift_value = normal_result ? highest_bit_index - (`DP_FP32_M - 1) : `DP_FP32_MIN_LSB - $signed(
    {{(32 - EXP_CALC_W) {lsb_value[EXP_CALC_W-1]}}, lsb_value}
  );
  assign shifted_magnitude = shift_value <= 0 ?
    {1'b0, magnitude} << (-shift_value) : {1'b0, magnitude} >> shift_value;
  // [RNE 决策] guard 是首个丢弃位，sticky 是更低位 OR；恰好半 ULP 时看保留 LSB。
  // 只有右移才可能进位；左移是补零，不制造舍入误差。
  generate
    for (bit_index = 0; bit_index < SUM_W; bit_index = bit_index + 1) begin : g_round_bits
      assign guard_candidates[bit_index]  = magnitude[bit_index] & (bit_index == shift_value - 1);
      assign sticky_candidates[bit_index] = magnitude[bit_index] & (bit_index < shift_value - 1);
    end
  endgenerate
  assign round_increment = (shift_value > 0) & (|guard_candidates) &
    ((|sticky_candidates) | shifted_magnitude[0]);
  assign rounded = shifted_magnitude + {{(ROUND_W - 1) {1'b0}}, round_increment};
  // [进位/打包] 24 位尾数舍入溢出时右规一位并增加指数；超出最大指数输出 Inf。
  // 非正规数舍入到最小正规数由位模式自然过渡；正负号与幅值最后合并。
  assign normalized = (normal_result & rounded[`DP_FP32_M]) ? rounded >> 1 : rounded;
  assign exponent_after_carry = exponent_value +
    {{(EXP_CALC_W - 1) {1'b0}}, (normal_result & rounded[`DP_FP32_M])};
  assign biased_exponent = exponent_after_carry + BIAS;
  assign finite_bits = normal_result ?
    (exponent_after_carry > MAX_EXP ? `DP_FP32_INF :
     {1'b0, biased_exponent[`DP_FP32_E-1:0], normalized[`DP_FP32_F-1:0]}) : rounded[`DP_FP32_W-1:0];
  assign out_bits = {sign_value, {(`DP_FP32_W - 1) {1'b0}}} | (active ? finite_bits : 0);
endmodule
