`include "dp_defs.vh"
// Nonnegative scale -> common E8M3. Special encodings remain explicit.
// Unsigned scale output. The biased exponent is separate.
// Precision / signal | S | I | F
// ------------------ | - | - | -
// E8M0               | 0 | 1 | 3
// E4M3               | 0 | 1 | 3
// E6M2               | 0 | 1 | 3
// Unit scale         | 0 | 1 | 3
module dp_scale_unpack (
  input wire [`DP_SCALE_W-1:0] in_data,
  input wire [`DP_SCALE_TYPE_W-1:0] in_datatype,
  output wire [`DP_SCALE_M-1:0] out_magnitude,
  output wire [`DP_EXP_W-1:0] out_exponent,
  output wire out_nan
);

  // [scale 统一编码] 输出非负 I1F3 幅值及公共 bias=127 的指数。
  // E8M0 的幅值恒为1；E6M2 补一个低零；E4M3 需区分正规/非正规 hidden bit。
  // NaN 以 out_nan 表达；out_magnitude=0 只是数值隔离，不表示把 NaN 当作零。
  wire is_e8m0;
  wire is_e6m2;
  wire is_e4m3;
  wire [31:0] exponent_work;
  wire [`DP_SCALE_M-1:0] decoded_magnitude;
  assign is_e8m0 = in_datatype == `DP_SC_E8M0;
  assign is_e6m2 = in_datatype == `DP_SC_E6M2;
  assign is_e4m3 = in_datatype == `DP_SC_E4M3;
  assign exponent_work = is_e8m0 ? {{(32 - `DP_SCALE_W) {1'b0}}, in_data} : is_e6m2 ?
    {{(32 - `DP_HIF_SCALE_E) {1'b0}}, in_data[`DP_HIF_SCALE_F+:`DP_HIF_SCALE_E]} + `DP_SCALE_BIAS -
    `DP_HIF_SCALE_BIAS :
    is_e4m3 ? (in_data[`DP_NV_SCALE_F+:`DP_NV_SCALE_E] == 0 ?
               32'd1 : {{(32 - `DP_NV_SCALE_E) {1'b0}}, in_data[`DP_NV_SCALE_F+:`DP_NV_SCALE_E]}) +
    `DP_SCALE_BIAS - `DP_NV_SCALE_BIAS : `DP_SCALE_BIAS;
  assign out_nan = ((is_e8m0 | is_e6m2) & (&in_data)) |
    (is_e4m3 & (&in_data[`DP_NV_SCALE_E+`DP_NV_SCALE_F-1:0]));
  assign decoded_magnitude = is_e6m2 ? {1'b1, in_data[`DP_HIF_SCALE_F-1:0], 1'b0} :
    is_e4m3 ? {|in_data[`DP_NV_SCALE_F+:`DP_NV_SCALE_E], in_data[`DP_NV_SCALE_F-1:0]} :
    {1'b1, {`DP_SCALE_F{1'b0}}};
  assign out_magnitude = out_nan ? 0 : decoded_magnitude;
  assign out_exponent = exponent_work[`DP_EXP_W-1:0];
endmodule
