`include "dp_defs.vh"
// One logical element of a packed 32-bit lane. INDEX is static, so synthesis
// removes unavailable T/H/Q routes. Combinational; S1 registers live in lane.
// S1 logical operand output (SM). Sign and exponent/class are separate.
// Precision / signal | S | I | F
// ------------------ | - | - | --
// TF32 / FP16        | 1 | 1 | 10
// BF16               | 1 | 1 | 7
// MXFP8 / MXFP6      | 1 | 1 | 3
// MXFP4 / NVFP4      | 1 | 3 | 1
// HiF4               | 1 | 2 | 2
// INT8               | 1 | 8 | 0
module dp_operand_unpack #(
  parameter integer INDEX = 0
) (
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [1:0] in_e1,
  input wire in_e2,
  output wire [`DP_NUM_W-1:0] out_number
);

  `include "dp_functions.vh"
  wire is_tf32;
  wire is_fp16;
  wire is_bf16;
  wire is_mx8_e4;
  wire is_mx8_e5;
  wire is_mx6_e3;
  wire is_mx6_e2;
  wire is_fp4;
  wire is_hif4;
  wire is_int8;
  wire is_binary_float;
  wire is_ieee;
  wire element_enabled;
  wire [31:0] raw_encoding;
  wire [31:0] exponent_field_width;
  wire [31:0] fraction_field_width;
  wire [31:0] exponent_bias;
  wire [31:0] exponent_field;
  wire [31:0] fraction_field;
  wire [31:0] exponent_mask;
  wire [31:0] fraction_mask;
  wire [31:0] finite_exponent;
  wire [31:0] finite_magnitude;
  wire [31:0] magnitude_work;
  wire [31:0] exponent_work;
  wire [`DP_EIGHTH_W-1:0] fp4_magnitude;
  wire negative;
  wire is_nan;
  wire is_inf;
  wire is_signaling;
  wire [`DP_NUM_CLASS_W-1:0] number_class;
  assign is_tf32 = in_datatype == `DP_DT_TF32;
  assign is_fp16 = in_datatype == `DP_DT_FP16;
  assign is_bf16 = in_datatype == `DP_DT_BF16;
  assign is_mx8_e4 = in_datatype == `DP_DT_MX8_E4M3;
  assign is_mx8_e5 = in_datatype == `DP_DT_MX8_E5M2;
  assign is_mx6_e3 = in_datatype == `DP_DT_MX6_E3M2;
  assign is_mx6_e2 = in_datatype == `DP_DT_MX6_E2M3;
  assign is_fp4 = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4);
  assign is_hif4 = in_datatype == `DP_DT_HIF4;
  assign is_int8 = in_datatype == `DP_DT_INT8;
  assign is_binary_float = ~(is_fp4 | is_hif4 | is_int8);
  assign is_ieee = is_tf32 | is_fp16 | is_bf16 | is_mx8_e5;
  assign element_enabled = INDEX < elements(in_datatype);
  // Constant-format selectors keep each encoding's field widths explicit.
  assign raw_encoding = is_tf32 ? in_data >> `DP_TF32_PAD : (is_fp16 | is_bf16) ? (
    in_data >> (INDEX * `DP_HALF_W)) & ((1 << `DP_HALF_W) - 1) : (is_mx8_e4 | is_mx8_e5 | is_int8) ?
    (in_data >> (INDEX * `DP_QUARTER_W)) & ((1 << `DP_QUARTER_W) - 1) : (is_mx6_e3 | is_mx6_e2) ?
    (in_data >> (INDEX * `DP_QUARTER_W + `DP_MX6_PAD)) &
    ((1 << `DP_MX6_W) - 1) : (in_data >> (INDEX * `DP_EIGHTH_W)) & ((1 << `DP_EIGHTH_W) - 1);
  assign exponent_field_width = (is_tf32 | is_bf16) ? `DP_FP32_E : (is_fp16 | is_mx8_e5) ?
    `DP_FP16_E : is_mx8_e4 ? `DP_MX8_E4_E : is_mx6_e3 ? `DP_MX6_E3_E : is_mx6_e2 ? `DP_MX6_E2_E : 0;
  assign fraction_field_width = (is_tf32 | is_fp16) ? `DP_FP16_F : is_bf16 ? `DP_BF16_F :
    (is_mx8_e4 | is_mx6_e2) ? `DP_MX8_E4_F : (is_mx8_e5 | is_mx6_e3) ? `DP_MX8_E5_F : 0;
  assign
    exponent_bias = (is_tf32 | is_bf16) ? `DP_FP32_BIAS : (is_fp16 | is_mx8_e5) ? `DP_FP16_BIAS :
    is_mx8_e4 ? `DP_MX8_E4_BIAS : is_mx6_e3 ? `DP_MX6_E3_BIAS : is_mx6_e2 ? `DP_MX6_E2_BIAS : 0;
  assign exponent_mask = (32'd1 << exponent_field_width) - 1;
  assign fraction_mask = (32'd1 << fraction_field_width) - 1;
  assign exponent_field = (raw_encoding >> fraction_field_width) & exponent_mask;
  assign fraction_field = raw_encoding & fraction_mask;
  assign is_nan = is_binary_float & (exponent_field == exponent_mask) &
    ((is_ieee & (fraction_field != 0)) | (is_mx8_e4 & (fraction_field == fraction_mask)));
  assign is_inf = is_binary_float & is_ieee & (exponent_field == exponent_mask) & ~is_nan;
  assign is_signaling = is_nan & is_ieee &
    ((fraction_field & (32'd1 << (fraction_field_width - 1))) == 0);
  assign negative = is_int8 ? raw_encoding[`DP_QUARTER_W-1] : (is_fp4 | is_hif4) ? raw_encoding[
    `DP_EIGHTH_W-1] : ((raw_encoding >> (exponent_field_width + fraction_field_width)) & 1) != 0;
  // E2M1 encoding magnitude table in F1: {0,1,2,3,4,6,8,12}.
  assign fp4_magnitude = raw_encoding[`DP_E_PAYLOAD_W-1:0] < 3'd5 ?
    {1'b0, raw_encoding[`DP_E_PAYLOAD_W-1:0]} : raw_encoding[`DP_E_PAYLOAD_W-1:0] == 3'd5 ? 4'd6 :
    raw_encoding[`DP_E_PAYLOAD_W-1:0] == 3'd6 ? 4'd8 : 4'd12;
  assign finite_exponent = (exponent_field == 0 ? 32'd1 : exponent_field) + (elements(
    in_datatype
  ) == `DP_Q_LANES ? `DP_Q_BIAS - exponent_bias : 0);
  assign finite_magnitude = ((exponent_field != 0 ? 32'd1 << fraction_field_width : 0) |
                             fraction_field) << (elements(
    in_datatype
  ) == `DP_Q_LANES ? `DP_SCALE_F - fraction_field_width : 0);
  assign magnitude_work = ~element_enabled ? 0 :
    is_int8 ? (negative ? (1 << `DP_QUARTER_W) - raw_encoding : raw_encoding) :
    is_hif4 ? {{(32 - `DP_E_PAYLOAD_W) {1'b0}}, raw_encoding[`DP_E_PAYLOAD_W-1:0]} <<
    in_e1[INDEX/`DP_E1_GRAIN] : is_fp4 ?
    {{(32 - `DP_EIGHTH_W) {1'b0}}, fp4_magnitude} : (is_nan | is_inf) ? 0 : finite_magnitude;
  assign exponent_work = ~element_enabled ? 0 :
    is_hif4 ? {31'b0, in_e2} : (is_fp4 | is_int8) ? 0 : (is_nan | is_inf) ? 1 : finite_exponent;
  assign number_class = ~element_enabled ? `DP_CLASS_ZERO : is_nan ? `DP_CLASS_NAN :
    is_inf ? `DP_CLASS_INF : magnitude_work == 0 ? `DP_CLASS_ZERO : `DP_CLASS_FINITE;
  assign out_number[`DP_NUM_MAG_LO+:`DP_MANT_W] = magnitude_work[`DP_MANT_W-1:0];
  assign out_number[`DP_NUM_EXP_LO+:`DP_EXP_W] = exponent_work[`DP_EXP_W-1:0];
  assign out_number[`DP_NUM_SIGN] = element_enabled & negative;
  assign out_number[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] = number_class;
  assign out_number[`DP_NUM_SIGNAL] = element_enabled & is_signaling;
endmodule
