`include "dp_defs.vh"
// One logical element of a packed 32-bit lane. INDEX is static, so synthesis
// removes unavailable T/H/Q routes. Combinational; S1 registers live in dp_lane_operand_unpack.
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
  // 静态元素槽号；生成期确定，超出当前格式容量时输出零记录。
  parameter integer INDEX = 0
) (
  // 单侧原始 32 位 lane 输入，按 datatype 解释各元素。
  // verilog_format: off
  input wire [`DP_LANE_W-1:0]       in_data,
  // 当前输入格式；按该格式完成 S1 译码。
  input wire [`DP_TYPE_W-1:0]       in_datatype,
  // HiF4 两个 e1 位，每位作用于四个元素，融入幅值一次。
  input wire [1:0]                  in_e1,
  // HiF4 lane 共享 e2 位，保留为后续指数增量。
  input wire                        in_e2,
  // 单元素无符号幅值，特殊值为零占位；高位补零不增加精度。
  output wire [`DP_MANT_W-1:0]      out_magnitude,
  // 有效偏置指数或 HiF4 e2，特殊值为 1 占位。
  output wire [`DP_EXP_W-1:0]       out_exponent,
  // 单元素符号，保留负零；非活动元素为零。
  output wire                       out_negative,
  // 单元素分类；后级不得从幅值或重编码指数重新判断 NaN/Inf。
  output wire [`DP_NUM_CLASS_W-1:0] out_class,
  // S1 每槽一位 sNaN 标志，供 A/B 配对生成 invalid。
  output wire                       out_signaling
  // verilog_format: on
);

  `include "dp_functions.vh"
  // [组合元素译码] INDEX 为 elaboration 常量；无效元素输出零幅值/指数/符号及 ZERO 分类。
  // 普通浮点分离符号/指数域/fraction 域，处理 hidden bit 与特殊分类；Q 重编码到共用坐标。
  // E/HiF4 是定点幅值编码，HiF4 e1 融入幅值，e2 仍作为独立指数字段输出。
  // verilog_format: off
  wire                       is_tf32;
  // FP16 输入格式选择。
  wire                       is_fp16;
  // BF16 输入格式选择。
  wire                       is_bf16;
  // MXFP8 E4M3 输入格式选择。
  wire                       is_mx8_e4;
  // MXFP8 E5M2 输入格式选择。
  wire                       is_mx8_e5;
  // MXFP6 E3M2 输入格式选择。
  wire                       is_mx6_e3;
  // MXFP6 E2M3 输入格式选择。
  wire                       is_mx6_e2;
  // MXFP4/NVFP4 共用 E2M1 元素译码。
  wire                       is_fp4;
  // HiF4 定点元素译码，e1 融入幅值。
  wire                       is_hif4;
  // 有符号 INT8 输入格式选择。
  wire                       is_int8;
  // 具有独立 exponent/fraction 编码的 T/H/Q 格式。
  wire                       is_binary_float;
  // 使用全 1 指数区分 Inf/NaN 的格式集合。
  wire                       is_ieee;
  // 该静态槽是否在当前格式容量内。
  wire                       element_enabled;
  // 提取到低位的当前元素原始编码；TF32/FP6 输入补零已移除。
  wire [31:0]                raw_encoding;
  // 原编码指数域的位数，区别于指数的数值。
  wire [31:0]                exponent_field_width;
  // 原编码显式 fraction 域的位数，不包含 hidden bit。
  wire [31:0]                fraction_field_width;
  // 原编码的指数偏置，供 Q 重编码保持数值。
  wire [31:0]                exponent_bias;
  // 原编码指数域的无符号数值。
  wire [31:0]                exponent_field;
  // 原编码显式 fraction 域的无符号数值。
  wire [31:0]                fraction_field;
  // 按指数域位数生成的低位掩码。
  wire [31:0]                exponent_mask;
  // 按 fraction 域位数生成的低位掩码。
  wire [31:0]                fraction_mask;
  // 有限数有效偏置指数；subnormal 按 e=1，Q 换为 bias=15。
  wire [31:0]                finite_exponent;
  // 有限 T/H/Q 幅值；恢复 hidden bit，Q 补到 F3。
  wire [31:0]                finite_magnitude;
  // 各格式选择后的 coefficient；特殊值置零，INT8 安全取绝对值。
  wire [31:0]                magnitude_work;
  // 各格式选择后的有效指数；E 仅 HiF4 保留 e2。
  wire [31:0]                exponent_work;
  // E2M1 值表转换为 I3F1 的无符号 coefficient。
  wire [`DP_EIGHTH_W-1:0]    fp4_magnitude;
  // 原始符号，保留负零，INT8 使用补码最高位。
  wire                       negative;
  // 按照原格式判定 NaN，不能使用重编码指数再次分类。
  wire                       is_nan;
  // 按照原格式判定 Inf；E4M3/FP6/E 类型不产生 Inf。
  wire                       is_inf;
  // IEEE 类格式的 signaling NaN 标志。
  wire                       is_signaling;
  // 互斥的 ZERO/FINITE/INF/NAN 分类，有限非零才可参与指数 MAX。
  wire [`DP_NUM_CLASS_W-1:0] number_class;
  assign is_tf32         = in_datatype == `DP_DT_TF32;
  assign is_fp16         = in_datatype == `DP_DT_FP16;
  assign is_bf16         = in_datatype == `DP_DT_BF16;
  assign is_mx8_e4       = in_datatype == `DP_DT_MX8_E4M3;
  assign is_mx8_e5       = in_datatype == `DP_DT_MX8_E5M2;
  assign is_mx6_e3       = in_datatype == `DP_DT_MX6_E3M2;
  assign is_mx6_e2       = in_datatype == `DP_DT_MX6_E2M3;
  assign is_fp4          = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4);
  assign is_hif4         = in_datatype == `DP_DT_HIF4;
  assign is_int8         = in_datatype == `DP_DT_INT8;
  assign is_binary_float = ~(is_fp4 | is_hif4 | is_int8);
  assign is_ieee         = is_tf32 | is_fp16 | is_bf16 | is_mx8_e5;
  assign element_enabled = INDEX < elements(in_datatype);
  // verilog_format: on
  // Constant-format selectors keep each encoding's field widths explicit.
  // verilog_format: off
  assign raw_encoding         = is_tf32                           ? in_data >> `DP_TF32_PAD :
                                (is_fp16 | is_bf16)               ? (in_data >> (INDEX * `DP_HALF_W)) & ((1 << `DP_HALF_W) - 1) :
                                (is_mx8_e4 | is_mx8_e5 | is_int8) ? (in_data >> (INDEX * `DP_QUARTER_W)) & ((1 << `DP_QUARTER_W) - 1) :
                                (is_mx6_e3 | is_mx6_e2)           ? (in_data >> (INDEX * `DP_QUARTER_W + `DP_MX6_PAD)) & ((1 << `DP_MX6_W) - 1) :
                                                                    (in_data >> (INDEX * `DP_EIGHTH_W)) & ((1 << `DP_EIGHTH_W) - 1);
  assign exponent_field_width = (is_tf32 | is_bf16)   ? `DP_FP32_E :
                                (is_fp16 | is_mx8_e5) ? `DP_FP16_E :
                                is_mx8_e4             ? `DP_MX8_E4_E :
                                is_mx6_e3             ? `DP_MX6_E3_E :
                                is_mx6_e2             ? `DP_MX6_E2_E :
                                                        0;
  assign fraction_field_width = (is_tf32 | is_fp16)     ? `DP_FP16_F :
                                is_bf16                 ? `DP_BF16_F :
                                (is_mx8_e4 | is_mx6_e2) ? `DP_MX8_E4_F :
                                (is_mx8_e5 | is_mx6_e3) ? `DP_MX8_E5_F :
                                                          0;
  assign exponent_bias        = (is_tf32 | is_bf16)   ? `DP_FP32_BIAS :
                                (is_fp16 | is_mx8_e5) ? `DP_FP16_BIAS :
                                is_mx8_e4             ? `DP_MX8_E4_BIAS :
                                is_mx6_e3             ? `DP_MX6_E3_BIAS :
                                is_mx6_e2             ? `DP_MX6_E2_BIAS :
                                                        0;
  assign exponent_mask        = (32'd1 << exponent_field_width) - 1;
  assign fraction_mask        = (32'd1 << fraction_field_width) - 1;
  assign exponent_field       = (raw_encoding >> fraction_field_width) & exponent_mask;
  assign fraction_field       = raw_encoding & fraction_mask;
  assign is_nan               = is_binary_float & (exponent_field == exponent_mask) & ((is_ieee & (fraction_field != 0)) | (is_mx8_e4 & (fraction_field == fraction_mask)));
  assign is_inf               = is_binary_float & is_ieee & (exponent_field == exponent_mask) & ~is_nan;
  assign is_signaling         = is_nan & is_ieee & ((fraction_field & (32'd1 << (fraction_field_width - 1))) == 0);
  assign negative             = is_int8            ? raw_encoding[`DP_QUARTER_W-1] :
                                (is_fp4 | is_hif4) ? raw_encoding[`DP_EIGHTH_W-1] :
                                                     ((raw_encoding >> (exponent_field_width + fraction_field_width)) & 1) != 0;
  // verilog_format: on
  // E2M1 encoding magnitude table in F1: {0,1,2,3,4,6,8,12}.
  // verilog_format: off
  assign fp4_magnitude    = raw_encoding[`DP_E_PAYLOAD_W-1:0] < 3'd5  ? {1'b0, raw_encoding[`DP_E_PAYLOAD_W-1:0]} :
                            raw_encoding[`DP_E_PAYLOAD_W-1:0] == 3'd5 ? 4'd6 :
                            raw_encoding[`DP_E_PAYLOAD_W-1:0] == 3'd6 ? 4'd8 :
                                                                        4'd12;
  assign finite_exponent  = (exponent_field == 0 ? 32'd1 : exponent_field) + (elements(in_datatype) == `DP_Q_LANES ? `DP_Q_BIAS - exponent_bias : 0);
  assign finite_magnitude = ((exponent_field != 0 ? 32'd1 << fraction_field_width : 0) | fraction_field) << (elements(in_datatype) == `DP_Q_LANES ? `DP_SCALE_F - fraction_field_width : 0);
  assign magnitude_work   = ~element_enabled  ? 0 :
                            is_int8           ? (negative ? (1 << `DP_QUARTER_W) - raw_encoding : raw_encoding) :
                            is_hif4           ? {{(32 - `DP_E_PAYLOAD_W) {1'b0}}, raw_encoding[`DP_E_PAYLOAD_W-1:0]} << in_e1[INDEX/`DP_E1_GRAIN] :
                            is_fp4            ? {{(32 - `DP_EIGHTH_W) {1'b0}}, fp4_magnitude} :
                            (is_nan | is_inf) ? 0 :
                                                finite_magnitude;
  assign exponent_work    = ~element_enabled   ? 0 :
                            is_hif4            ? {31'b0, in_e2} :
                            (is_fp4 | is_int8) ? 0 :
                            (is_nan | is_inf)  ? 1 :
                                                 finite_exponent;
  assign number_class     = ~element_enabled    ? `DP_CLASS_ZERO :
                            is_nan              ? `DP_CLASS_NAN :
                            is_inf              ? `DP_CLASS_INF :
                            magnitude_work == 0 ? `DP_CLASS_ZERO :
                                                  `DP_CLASS_FINITE;
  assign out_magnitude    = magnitude_work[`DP_MANT_W-1:0];
  assign out_exponent     = exponent_work[`DP_EXP_W-1:0];
  assign out_negative     = element_enabled & negative;
  assign out_class        = number_class;
  assign out_signaling    = element_enabled & is_signaling;
  // verilog_format: on
endmodule
