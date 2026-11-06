`include "dp_defs.vh"
// S5 combinational C decode. Raw C travels through S1-S4 without decoding.
// Both FP32 and INT32 produce sign plus M32; FP32 adds eight structural low zeros.
// S5 C magnitude. Sign travels separately.
// Precision / signal | S | I  | F
// ------------------ | - | -- | --
// FP32 natural M24   | 0 | 1  | 23
// FP32 padded M32    | 0 | 1  | 31
// INT32 absolute M32 | 0 | 32 | 0
module dp_c_unpack #(
  parameter integer ANCHOR_W = 10
) (
  input wire [`DP_FP32_W-1:0] in_data,
  input wire in_datatype,
  output wire out_negative,
  output wire [`DP_FP32_W-1:0] out_magnitude,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  output wire [$clog2(`DP_FP32_W+1)-1:0] out_z,
  output wire [`DP_SPECIAL_W-1:0] out_special
);

  // [S5 C token] FP32 分离符号与 24 位有效数后低补零到 M32；INT32 取完整绝对值。
  // 浮点 subnormal 使用有效指数 1-bias；NaN/Inf 单独分类；零 anchor 为占位值。
  localparam signed [ANCHOR_W-1:0] EXPONENT_BIAS = `DP_FP32_BIAS;
  wire [`DP_FP32_E-1:0] exponent_field;
  wire [`DP_FP32_F-1:0] fraction_field;
  wire signed [ANCHOR_W-1:0] exponent_unbiased;
  wire is_integer;
  wire is_special;
  wire has_fraction;
  wire magnitude_active;
  wire [$clog2(`DP_FP32_W+1)-1:0] leading_zero_count;
  assign exponent_field = in_data[`DP_FP32_F+:`DP_FP32_E];
  assign fraction_field = in_data[0+:`DP_FP32_F];
  assign is_integer = in_datatype == `DP_CT_INT32;
  assign is_special = ~is_integer & (&exponent_field);
  assign has_fraction = |fraction_field;
  assign exponent_unbiased = (exponent_field == 0 ? {{(ANCHOR_W - 1) {1'b0}}, 1'b1} : $signed(
    {{(ANCHOR_W - `DP_FP32_E) {1'b0}}, exponent_field}
  )) - EXPONENT_BIAS;
  assign out_negative = in_data[`DP_FP32_W-1];
  assign out_magnitude = is_integer ? (out_negative ? -in_data : in_data) :
    is_special ? 0 : {|exponent_field, fraction_field, {(`DP_FP32_W - `DP_FP32_M) {1'b0}}};
  assign out_anchor = (~is_integer & ~is_special & (out_magnitude != 0)) ? exponent_unbiased : 0;
  assign out_special[`DP_SP_NAN] = is_special & has_fraction;
  assign out_special[`DP_SP_INVALID] = is_special & has_fraction & ~fraction_field[`DP_FP32_F-1];
  assign out_special[`DP_SP_POS_INF] = is_special & ~has_fraction & ~out_negative;
  assign out_special[`DP_SP_NEG_INF] = is_special & ~has_fraction & out_negative;
  dp_lzd #(
    .W(`DP_FP32_W)
  ) u_subnormal_detect (
    .in_magnitude(out_magnitude),
    .out_count(leading_zero_count),
    .out_active(magnitude_active)
  );
  assign out_z = (~is_integer & (out_special == 0)) ? leading_zero_count : 0;
endmodule
