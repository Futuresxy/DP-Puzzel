`include "dp_defs.vh"
// Q 单元素组合解包：MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3。
// 无寄存；幅值U4 S0I1F3，指数U5统一bias15，保留特殊值及负零。
module dp_operand_unpack_q #(
  // Q 字节槽编号，合法范围 0..3。
  parameter integer INDEX = 0
) (
  // 一个 lane 的原始操作数。
  input wire [`DP_LANE_W-1:0] in_data,
  // 仅四种 Q 格式。
  input wire [`DP_TYPE_W-1:0] in_datatype,
  // 四位无符号 coefficient；符号和分类独立。
  output wire [`DP_EIGHTH_W-1:0] out_magnitude,
  // Q 有效偏置指数 U5，统一 bias=15。
  output wire [`DP_Q_EXP_W-1:0] out_exponent,
  // 原始符号，包括负零。
  output wire out_negative,
  // ZERO/FINITE/INF/NAN 分类。
  output wire [`DP_NUM_CLASS_W-1:0] out_class,
  // E5M2 的 signaling NaN 标志。
  output wire out_signaling
);
  // 固定 Q 字节槽偏移。
  localparam integer Q_OFFSET = INDEX * `DP_QUARTER_W;
  // Q 的统一 bias 与各编码 bias 之差，显式限定为 U5。
  localparam [`DP_Q_EXP_W-1:0] E4_BIAS_DELTA = `DP_Q_BIAS - `DP_MX8_E4_BIAS;
  localparam [`DP_Q_EXP_W-1:0] E3_BIAS_DELTA = `DP_Q_BIAS - `DP_MX6_E3_BIAS;
  localparam [`DP_Q_EXP_W-1:0] E2_BIAS_DELTA = `DP_Q_BIAS - `DP_MX6_E2_BIAS;

  // 四种互斥格式选择。
  wire select_e4;
  wire select_e5;
  wire select_e3;
  wire select_e2;
  wire select_q;
  // verilog_format: off
  assign select_e4   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX8_E4M3);
  assign select_e5   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX8_E5M2);
  assign select_e3   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX6_E3M2);
  assign select_e2   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX6_E2M3);
  assign select_q    = select_e4 | select_e5 | select_e3 | select_e2;
  // verilog_format: on

  // Q 按固定编码域切片；FP6 在高六位，低两位不是 fraction。
  wire [`DP_QUARTER_W-1:0] q_encoding;
  wire [`DP_MX8_E4_E-1:0] e4_exponent_field;
  wire [`DP_MX8_E5_E-1:0] e5_exponent_field;
  wire [`DP_MX6_E3_E-1:0] e3_exponent_field;
  wire [`DP_MX6_E2_E-1:0] e2_exponent_field;
  // verilog_format: off
  assign q_encoding        = in_data[Q_OFFSET+:`DP_QUARTER_W];
  assign e4_exponent_field = q_encoding[`DP_MX8_E4_F+:`DP_MX8_E4_E];
  assign e5_exponent_field = q_encoding[`DP_MX8_E5_F+:`DP_MX8_E5_E];
  assign e3_exponent_field = q_encoding[(`DP_MX6_PAD+`DP_MX6_E3_F)+:`DP_MX6_E3_E];
  assign e2_exponent_field = q_encoding[(`DP_MX6_PAD+`DP_MX6_E2_F)+:`DP_MX6_E2_E];
  // verilog_format: on

  // 非正规有效指数用 1；四种模式在窄字段内重编码到 bias=15。
  wire [`DP_Q_EXP_W-1:0] e4_exponent;
  wire [`DP_Q_EXP_W-1:0] e5_exponent;
  wire [`DP_Q_EXP_W-1:0] e3_exponent;
  wire [`DP_Q_EXP_W-1:0] e2_exponent;
  wire [`DP_Q_EXP_W-1:0] finite_exponent;
  // verilog_format: off
  assign e4_exponent = ((|e4_exponent_field) ? {{(`DP_Q_EXP_W-`DP_MX8_E4_E){1'b0}}, e4_exponent_field} : {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1}) + E4_BIAS_DELTA;
  assign e5_exponent = (|e5_exponent_field) ? e5_exponent_field : {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1};
  assign e3_exponent = ((|e3_exponent_field) ? {{(`DP_Q_EXP_W-`DP_MX6_E3_E){1'b0}}, e3_exponent_field} : {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1}) + E3_BIAS_DELTA;
  assign e2_exponent = ((|e2_exponent_field) ? {{(`DP_Q_EXP_W-`DP_MX6_E2_E){1'b0}}, e2_exponent_field} : {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1}) + E2_BIAS_DELTA;
  assign finite_exponent = ({`DP_Q_EXP_W{select_e4}} & e4_exponent) |
                           ({`DP_Q_EXP_W{select_e5}} & e5_exponent) |
                           ({`DP_Q_EXP_W{select_e3}} & e3_exponent) |
                           ({`DP_Q_EXP_W{select_e2}} & e2_exponent);
  // verilog_format: on

  // Q 幅值统一 F3：两位 fraction 的模式静态低补一零。
  wire [`DP_EIGHTH_W-1:0] q_magnitude;
  // verilog_format: off
  assign q_magnitude = ({`DP_EIGHTH_W{select_e4}} & {(|e4_exponent_field), q_encoding[0+:`DP_MX8_E4_F]}) |
                       ({`DP_EIGHTH_W{select_e5}} & {(|e5_exponent_field), q_encoding[0+:`DP_MX8_E5_F], 1'b0}) |
                       ({`DP_EIGHTH_W{select_e3}} & {(|e3_exponent_field), q_encoding[`DP_MX6_PAD+:`DP_MX6_E3_F], 1'b0}) |
                       ({`DP_EIGHTH_W{select_e2}} & {(|e2_exponent_field), q_encoding[`DP_MX6_PAD+:`DP_MX6_E2_F]});
  // verilog_format: on

  // E4M3 只有全 1 幅值编码为 NaN；E5M2 采用 IEEE Inf/NaN/sNaN 分类。
  wire is_nan;
  wire is_inf;
  wire is_special;
  // verilog_format: off
  assign is_nan       = (select_e4 & (&e4_exponent_field) & (&q_encoding[0+:`DP_MX8_E4_F])) |
                        (select_e5 & (&e5_exponent_field) & (|q_encoding[0+:`DP_MX8_E5_F]));
  assign is_inf       = select_e5 & (&e5_exponent_field) & ~(|q_encoding[0+:`DP_MX8_E5_F]);
  assign is_special   = is_nan | is_inf;
  assign out_signaling = select_e5 & is_nan & ~q_encoding[`DP_MX8_E5_F-1];
  assign out_magnitude = is_special ? {`DP_EIGHTH_W{1'b0}} : q_magnitude;
  assign out_exponent  = is_special ? {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1} : finite_exponent;
  assign out_negative  = select_q & q_encoding[`DP_QUARTER_W-1];
  assign out_class     = is_nan ? `DP_CLASS_NAN : is_inf ? `DP_CLASS_INF :
                         (|q_magnitude) ? `DP_CLASS_FINITE : `DP_CLASS_ZERO;
  // verilog_format: on
endmodule
