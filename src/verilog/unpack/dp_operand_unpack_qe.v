`include "dp_defs.vh"
// QE 单元素组合解包：固定字段切片和窄 MUX，无 T/H/INT8 或运行时域宽计算。
// INDEX 是逻辑元素号：Q 使用 0..3，E 使用 0..7；未用槽输出零。
// 无寄存器；调用者保存 S1。NaN/Inf 的数值占位为 M=0/E=1，分类独立。
// 幅值格式（独立符号不计入本表）：
// 精度             | S | I | F
// MXFP8 / MXFP6    | 0 | 1 | 3
// MXFP4 / NVFP4    | 0 | 3 | 1
// HiF4（融合 e1） | 0 | 2 | 2
module dp_operand_unpack_qe #(
  // elaboration 期元素槽；低四槽可以解释为 Q 或 E，高四槽只解释为 E。
  parameter integer INDEX = 0
) (
  // 一个 lane 的原始操作数。
  input wire [`DP_LANE_W-1:0] in_data,
  // 合法格式仅四种 Q 与三种 E。
  input wire [`DP_TYPE_W-1:0] in_datatype,
  // HiF4 每四个元素共享一个 e1，融合到幅值一次。
  input wire [1:0] in_e1,
  // HiF4 整条 lane 共享的 e2，作为指数旁带。
  input wire in_e2,
  // 四位无符号 coefficient；符号和分类独立。
  output wire [`DP_EIGHTH_W-1:0] out_magnitude,
  // Q 有效偏置指数 U5；E 为 e2 或零。
  output wire [`DP_Q_EXP_W-1:0] out_exponent,
  // 原始符号，包括负零。
  output wire out_negative,
  // ZERO/FINITE/INF/NAN 分类。
  output wire [`DP_NUM_CLASS_W-1:0] out_class,
  // E5M2 的 signaling NaN 标志。
  output wire out_signaling
);
  // 固定 Q 槽偏移；高四槽取模仅防止未选分支出现越界切片。
  localparam integer Q_OFFSET = (INDEX % `DP_Q_LANES) * `DP_QUARTER_W;
  // Q 的统一 bias 与各编码 bias 之差，显式限定为 U5。
  localparam [`DP_Q_EXP_W-1:0] E4_BIAS_DELTA = `DP_Q_BIAS - `DP_MX8_E4_BIAS;
  localparam [`DP_Q_EXP_W-1:0] E3_BIAS_DELTA = `DP_Q_BIAS - `DP_MX6_E3_BIAS;
  localparam [`DP_Q_EXP_W-1:0] E2_BIAS_DELTA = `DP_Q_BIAS - `DP_MX6_E2_BIAS;

  // 互斥格式选择，低四槽才生成 Q 逻辑。
  wire select_e4;
  wire select_e5;
  wire select_e3;
  wire select_e2;
  wire select_fp4;
  wire select_hif4;
  wire select_q;
  wire select_e;
  // verilog_format: off
  assign select_e4   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX8_E4M3);
  assign select_e5   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX8_E5M2);
  assign select_e3   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX6_E3M2);
  assign select_e2   = (INDEX < `DP_Q_LANES) & (in_datatype == `DP_DT_MX6_E2M3);
  assign select_fp4  = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4);
  assign select_hif4 = in_datatype == `DP_DT_HIF4;
  assign select_q    = select_e4 | select_e5 | select_e3 | select_e2;
  assign select_e    = select_fp4 | select_hif4;
  // verilog_format: on

  // Q 按固定编码域切片；FP6 在高六位，低两位不是 fraction。
  wire [`DP_QUARTER_W-1:0] q_encoding;
  wire [`DP_MX8_E4_E-1:0] e4_exponent_field;
  wire [`DP_MX8_E5_E-1:0] e5_exponent_field;
  wire [`DP_MX6_E3_E-1:0] e3_exponent_field;
  wire [`DP_MX6_E2_E-1:0] e2_exponent_field;
  wire [`DP_E_PAYLOAD_W-1:0] e_payload;
  // verilog_format: off
  assign q_encoding        = in_data[Q_OFFSET+:`DP_QUARTER_W];
  assign e4_exponent_field = q_encoding[`DP_MX8_E4_F+:`DP_MX8_E4_E];
  assign e5_exponent_field = q_encoding[`DP_MX8_E5_F+:`DP_MX8_E5_E];
  assign e3_exponent_field = q_encoding[(`DP_MX6_PAD+`DP_MX6_E3_F)+:`DP_MX6_E3_E];
  assign e2_exponent_field = q_encoding[(`DP_MX6_PAD+`DP_MX6_E2_F)+:`DP_MX6_E2_E];
  assign e_payload          = in_data[INDEX*`DP_EIGHTH_W+:`DP_E_PAYLOAD_W];
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
                           ({`DP_Q_EXP_W{select_e2}} & e2_exponent) |
                           {{(`DP_Q_EXP_W-1){1'b0}}, (select_hif4 & in_e2)};
  // verilog_format: on

  // Q 幅值统一 F3：两位 fraction 的模式静态低补一零。
  wire [`DP_EIGHTH_W-1:0] q_magnitude;
  // E2M1 的整数 coefficient 查表，实际值为 coefficient * 2^-1。
  wire [`DP_EIGHTH_W-1:0] fp4_magnitude;
  // HiF4 左移仅 0/1 位，用明确二选一保留完整四位。
  wire [`DP_EIGHTH_W-1:0] hif4_magnitude;
  wire [`DP_EIGHTH_W-1:0] finite_magnitude;
  // verilog_format: off
  assign q_magnitude = ({`DP_EIGHTH_W{select_e4}} & {(|e4_exponent_field), q_encoding[0+:`DP_MX8_E4_F]}) |
                       ({`DP_EIGHTH_W{select_e5}} & {(|e5_exponent_field), q_encoding[0+:`DP_MX8_E5_F], 1'b0}) |
                       ({`DP_EIGHTH_W{select_e3}} & {(|e3_exponent_field), q_encoding[`DP_MX6_PAD+:`DP_MX6_E3_F], 1'b0}) |
                       ({`DP_EIGHTH_W{select_e2}} & {(|e2_exponent_field), q_encoding[`DP_MX6_PAD+:`DP_MX6_E2_F]});
  // payload 0..4 原值，5/6/7 分别对应 coefficient 6/8/12。
  assign fp4_magnitude = (e_payload < 3'd5)  ? {1'b0, e_payload} :
                         (e_payload == 3'd5) ? 4'd6 :
                         (e_payload == 3'd6) ? 4'd8 : 4'd12;
  assign hif4_magnitude = in_e1[INDEX/`DP_E1_GRAIN] ? {e_payload, 1'b0} : {1'b0, e_payload};
  assign finite_magnitude = q_magnitude |
                            ({`DP_EIGHTH_W{select_fp4}} & fp4_magnitude) |
                            ({`DP_EIGHTH_W{select_hif4}} & hif4_magnitude);
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
  assign out_magnitude = is_special ? {`DP_EIGHTH_W{1'b0}} : finite_magnitude;
  assign out_exponent  = is_special ? {{(`DP_Q_EXP_W-1){1'b0}}, 1'b1} : finite_exponent;
  assign out_negative  = (select_q & q_encoding[`DP_QUARTER_W-1]) |
                         (select_e & in_data[INDEX*`DP_EIGHTH_W+`DP_EIGHTH_W-1]);
  assign out_class     = is_nan ? `DP_CLASS_NAN : is_inf ? `DP_CLASS_INF :
                         (|finite_magnitude) ? `DP_CLASS_FINITE : `DP_CLASS_ZERO;
  // verilog_format: on
endmodule
