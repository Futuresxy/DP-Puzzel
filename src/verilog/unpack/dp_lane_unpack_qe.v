`include "dp_defs.vh"
// QE S1 紧凑解包：数值按 M32/E20 atom 保存，配对分类在寄存前归约。
// 只存乘积符号/活动位/四位特殊摘要，不再存 A/B 两套 class/sNaN/sign。
// 同步低有效 rst_n；payload 仅在有效时更新。valid 由父 lane 逐拍推进。
// 延迟一个寄存边界，S2 数值 bank 接口、后续算术和 L8 均不改变。
// 幅值 S/I/F：Q S0I1F3；MX/NV S0I3F1；HiF4 S0I2F2。
// 符号独立，包括负零；指数 Q 为 U5，HiF4 为共享 e2，MX/NV 为零。
module dp_lane_unpack_qe (
  // 上升沿捕获 S1 数据。
  input wire clock,
  // 同步低有效复位，通过父层 valid 屏蔽未初始化 payload。
  input wire rst_n,
  // 本拍合法 Q/E 请求有效。
  input wire in_valid,
  // 本拍格式；配对摘要和数值字段都依据同一请求生成。
  input wire [`DP_TYPE_W-1:0] in_datatype,
  // 父 lane 同拍保存的 S1 类型，用于屏蔽关闭字段的旧值/未初始化值。
  input wire [`DP_TYPE_W-1:0] in_registered_datatype,
  // 原始 A/B lane 编码，各 32 位。
  input wire [`DP_LANE_W-1:0] in_a,
  input wire [`DP_LANE_W-1:0] in_b,
  // HiF4 每四项一位 e1，每八项一位 e2。
  input wire [1:0] in_e1_a,
  input wire [1:0] in_e1_b,
  input wire in_e2_a,
  input wire in_e2_b,
  // S1 紧凑幅值，各含两个 M16 atom。
  output wire [`DP_UNPACK_MANT_W-1:0] out_a_mantissas,
  output wire [`DP_UNPACK_MANT_W-1:0] out_b_mantissas,
  // S1 紧凑指数，各含两个 E10 atom，保持原 bank 位片合同。
  output wire [`DP_UNPACK_EXP_W-1:0] out_a_exponents,
  output wire [`DP_UNPACK_EXP_W-1:0] out_b_exponents,
  // S1 逻辑顺序 Q0..3/E0..7 的乘积符号，未用槽清零。
  output wire [`DP_E_LANES-1:0] out_product_negative,
  // 有限非零 A/B 配对，供 S2 指数 MAX 使用，不能代替参与位。
  output wire [`DP_E_LANES-1:0] out_product_active,
  // 配对后归约的 NaN/invalid/正负 Inf 摘要。
  output wire [`DP_SPECIAL_W-1:0] out_special,
  // 所有原始参与乘积符号为负，零项也参与。
  output wire out_all_negative
);
  // E 模式使用全部八槽；Q 只使用逻辑槽 0..3。
  wire select_e;
  assign select_e = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) |
                    (in_datatype == `DP_DT_HIF4);
  // 源级 HiF4 需要保存 e2；目的级类型决定输出字段恢复。
  wire select_hif4;
  wire r1_select_e;
  wire r1_select_hif4;
  // verilog_format: off
  assign select_hif4    = in_datatype == `DP_DT_HIF4;
  assign r1_select_e    = (in_registered_datatype == `DP_DT_MXFP4) | (in_registered_datatype == `DP_DT_NVFP4) | (in_registered_datatype == `DP_DT_HIF4);
  assign r1_select_hif4 = in_registered_datatype == `DP_DT_HIF4;
  // verilog_format: on
  // A 逐元素四位无符号幅值，常量 generate 索引。
  wire [`DP_EIGHTH_W-1:0] a_magnitudes[0:`DP_E_LANES-1];
  // A 逐元素五位重编码指数，常量 generate 索引。
  wire [`DP_Q_EXP_W-1:0] a_exponents[0:`DP_E_LANES-1];
  // A 逐元素分类，仅组合使用，常量 generate 索引。
  wire [`DP_NUM_CLASS_W-1:0] a_classes[0:`DP_E_LANES-1];
  // A 原始符号，在 S1 前配对，不单独寄存。
  wire [`DP_E_LANES-1:0] a_negative;
  // A sNaN 标志，在 S1 前配对，不单独寄存。
  wire [`DP_E_LANES-1:0] a_signaling;
  // B 逐元素四位无符号幅值，常量 generate 索引。
  wire [`DP_EIGHTH_W-1:0] b_magnitudes[0:`DP_E_LANES-1];
  // B 逐元素五位重编码指数，常量 generate 索引。
  wire [`DP_Q_EXP_W-1:0] b_exponents[0:`DP_E_LANES-1];
  // B 逐元素分类，仅组合使用，常量 generate 索引。
  wire [`DP_NUM_CLASS_W-1:0] b_classes[0:`DP_E_LANES-1];
  // B 原始符号，在 S1 前配对，不单独寄存。
  wire [`DP_E_LANES-1:0] b_negative;
  // B sNaN 标志，在 S1 前配对，不单独寄存。
  wire [`DP_E_LANES-1:0] b_signaling;
  // S1 前组合生成的乘积 XOR 符号。
  wire [`DP_E_LANES-1:0] product_negative_d;
  // S1 前组合生成的有限非零配对活动位。
  wire [`DP_E_LANES-1:0] product_active_d;
  // S1 前组合生成的参与项 NaN。
  wire [`DP_E_LANES-1:0] nan_sources;
  // S1 前组合生成的参与项 sNaN 或 0×Inf。
  wire [`DP_E_LANES-1:0] invalid_sources;
  // S1 前组合生成的参与项正 Inf。
  wire [`DP_E_LANES-1:0] positive_inf_sources;
  // S1 前组合生成的参与项负 Inf。
  wire [`DP_E_LANES-1:0] negative_inf_sources;
  // S1 前组合生成的未用槽置一的全负归约输入。
  wire [`DP_E_LANES-1:0] included_negative;
  // 解码与配对共用逻辑元素号，不经过 atom 分类重排。
  genvar element_index;
  // 紧凑数值接口的 atom 号。
  genvar atom_index;
  genvar slot_index;
  generate
    for (element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1) begin : g_decode_pair
      dp_operand_unpack_qe #(.INDEX(element_index)) u_operand_a (
        .in_data       (in_a),
        .in_datatype   (in_datatype),
        .in_e1         (in_e1_a),
        .in_e2         (in_e2_a),
        .out_magnitude (a_magnitudes[element_index]),
        .out_exponent  (a_exponents[element_index]),
        .out_negative  (a_negative[element_index]),
        .out_class     (a_classes[element_index]),
        .out_signaling (a_signaling[element_index])
      );
      dp_operand_unpack_qe #(.INDEX(element_index)) u_operand_b (
        .in_data       (in_b),
        .in_datatype   (in_datatype),
        .in_e1         (in_e1_b),
        .in_e2         (in_e2_b),
        .out_magnitude (b_magnitudes[element_index]),
        .out_exponent  (b_exponents[element_index]),
        .out_negative  (b_negative[element_index]),
        .out_class     (b_classes[element_index]),
        .out_signaling (b_signaling[element_index])
      );
      // 必须先按元素配对，不能将 A/B 各自的 Inf/Zero 先归约后交叉组合。
      wire element_used;
      wire pair_nan;
      wire pair_inf;
      wire pair_zero;
      wire pair_infinity;
      // verilog_format: off
      assign element_used                          = select_e | (element_index < `DP_Q_LANES);
      assign pair_nan                              = (a_classes[element_index] == `DP_CLASS_NAN) | (b_classes[element_index] == `DP_CLASS_NAN);
      assign pair_inf                              = (a_classes[element_index] == `DP_CLASS_INF) | (b_classes[element_index] == `DP_CLASS_INF);
      assign pair_zero                             = (a_classes[element_index] == `DP_CLASS_ZERO) | (b_classes[element_index] == `DP_CLASS_ZERO);
      assign pair_infinity                         = element_used & pair_inf & ~pair_zero & ~pair_nan;
      assign product_negative_d[element_index]     = element_used & (a_negative[element_index] ^ b_negative[element_index]);
      assign product_active_d[element_index]       = element_used & (a_classes[element_index] == `DP_CLASS_FINITE) & (b_classes[element_index] == `DP_CLASS_FINITE);
      assign nan_sources[element_index]           = element_used & pair_nan;
      assign invalid_sources[element_index]       = element_used & (a_signaling[element_index] | b_signaling[element_index] | (pair_inf & pair_zero));
      assign positive_inf_sources[element_index]  = pair_infinity & ~product_negative_d[element_index];
      assign negative_inf_sources[element_index]  = pair_infinity & product_negative_d[element_index];
      assign included_negative[element_index]     = ~element_used | product_negative_d[element_index];
      // verilog_format: on
    end

    // 保持 bank 的 M16/E10 atom 接口。结构零是连线，不扩展成通用 Number。
    for (atom_index = 0; atom_index < `DP_LANES; atom_index = atom_index + 1) begin : g_atom
      // A E atom 四个连续 nibble。
      wire [`DP_HALF_W-1:0] a_e_mantissas;
      // A Q atom 两个 nibble，占 M16 的低八位。
      wire [`DP_HALF_W-1:0] a_q_mantissas;
      // A 待捕获的幅值和指数，各模式使用原紧凑布局。
      wire [`DP_HALF_W-1:0] a_mantissas_d;
      wire [`DP_UNPACK_ATOM_EXP_W-1:0] a_exponents_d;
      // verilog_format: off
      assign a_q_mantissas = {{(`DP_HALF_W-`DP_UNPACK_ATOM_Q_LANES*`DP_EIGHTH_W){1'b0}}, a_magnitudes[atom_index*`DP_UNPACK_ATOM_Q_LANES+1], a_magnitudes[atom_index*`DP_UNPACK_ATOM_Q_LANES]};
      assign a_mantissas_d = select_e ? a_e_mantissas : a_q_mantissas;
      assign a_exponents_d = select_e ? {{(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, a_exponents[0][0]} :
                                              {a_exponents[atom_index*`DP_UNPACK_ATOM_Q_LANES+1], a_exponents[atom_index*`DP_UNPACK_ATOM_Q_LANES]};
      // verilog_format: on
      // B E atom 四个连续 nibble。
      wire [`DP_HALF_W-1:0] b_e_mantissas;
      // B Q atom 两个 nibble，占 M16 的低八位。
      wire [`DP_HALF_W-1:0] b_q_mantissas;
      // B 待捕获的幅值和指数，各模式使用原紧凑布局。
      wire [`DP_HALF_W-1:0] b_mantissas_d;
      wire [`DP_UNPACK_ATOM_EXP_W-1:0] b_exponents_d;
      // verilog_format: off
      assign b_q_mantissas = {{(`DP_HALF_W-`DP_UNPACK_ATOM_Q_LANES*`DP_EIGHTH_W){1'b0}}, b_magnitudes[atom_index*`DP_UNPACK_ATOM_Q_LANES+1], b_magnitudes[atom_index*`DP_UNPACK_ATOM_Q_LANES]};
      assign b_mantissas_d = select_e ? b_e_mantissas : b_q_mantissas;
      assign b_exponents_d = select_e ? {{(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, b_exponents[0][0]} :
                                              {b_exponents[atom_index*`DP_UNPACK_ATOM_Q_LANES+1], b_exponents[atom_index*`DP_UNPACK_ATOM_Q_LANES]};
      // verilog_format: on
      for (slot_index = 0; slot_index < `DP_UNPACK_ATOM_SIGN_W; slot_index = slot_index + 1) begin : g_mantissa_slot
        assign a_e_mantissas[slot_index*`DP_EIGHTH_W+:`DP_EIGHTH_W] = a_magnitudes[atom_index*`DP_UNPACK_ATOM_SIGN_W+slot_index];
        assign b_e_mantissas[slot_index*`DP_EIGHTH_W+:`DP_EIGHTH_W] = b_magnitudes[atom_index*`DP_UNPACK_ATOM_SIGN_W+slot_index];
      end
      // S1 指数拆分：Q 使用完整 E10，HiF4 只用最低 e2 位，MX/NV 全零。
      // 写使能看当前请求，输出恢复看 r1 类型，允许连续 Q/E 切换。
      // A 指数低位可供 Q/HiF4 共用，高位仅 Q 捕获。
      wire r1_a_exponent_low;
      wire [`DP_UNPACK_ATOM_EXP_W-2:0] r1_a_exponent_high;
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_HALF_W))
      ff_s0_s1_a_mantissas (.clock(clock), .in_en(rst_n & in_valid), .in_d(a_mantissas_d), .out_q(out_a_mantissas[atom_index*`DP_HALF_W+:`DP_HALF_W]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s0_s1_a_exponent_low (.clock(clock), .in_en(rst_n & in_valid & (~select_e | select_hif4)), .in_d(a_exponents_d[0]), .out_q(r1_a_exponent_low));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_EXP_W-1))
      ff_s0_s1_a_exponent_high (.clock(clock), .in_en(rst_n & in_valid & ~select_e), .in_d(a_exponents_d[`DP_UNPACK_ATOM_EXP_W-1:1]), .out_q(r1_a_exponent_high));
      assign out_a_exponents[atom_index*`DP_UNPACK_ATOM_EXP_W+:`DP_UNPACK_ATOM_EXP_W] = r1_select_e ? { {(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, (r1_select_hif4 ? r1_a_exponent_low : 1'b0) } : {r1_a_exponent_high, r1_a_exponent_low};
      // verilog_format: on
      // B 指数低位可供 Q/HiF4 共用，高位仅 Q 捕获。
      wire r1_b_exponent_low;
      wire [`DP_UNPACK_ATOM_EXP_W-2:0] r1_b_exponent_high;
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_HALF_W))
      ff_s0_s1_b_mantissas (.clock(clock), .in_en(rst_n & in_valid), .in_d(b_mantissas_d), .out_q(out_b_mantissas[atom_index*`DP_HALF_W+:`DP_HALF_W]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s0_s1_b_exponent_low (.clock(clock), .in_en(rst_n & in_valid & (~select_e | select_hif4)), .in_d(b_exponents_d[0]), .out_q(r1_b_exponent_low));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_EXP_W-1))
      ff_s0_s1_b_exponent_high (.clock(clock), .in_en(rst_n & in_valid & ~select_e), .in_d(b_exponents_d[`DP_UNPACK_ATOM_EXP_W-1:1]), .out_q(r1_b_exponent_high));
      assign out_b_exponents[atom_index*`DP_UNPACK_ATOM_EXP_W+:`DP_UNPACK_ATOM_EXP_W] = r1_select_e ? { {(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, (r1_select_hif4 ? r1_b_exponent_low : 1'b0) } : {r1_b_exponent_high, r1_b_exponent_low};
      // verilog_format: on
    end
  endgenerate

  // S1 配对摘要寄存。all_negative 包括零项；Inf 冲突独立于数值活动位。
  wire [`DP_SPECIAL_W-1:0] special_flags_d;
  wire all_negative_d;
  // verilog_format: off
  assign special_flags_d[`DP_SP_NAN]     = |nan_sources;
  assign special_flags_d[`DP_SP_INVALID] = (|invalid_sources) | ((|positive_inf_sources) & (|negative_inf_sources));
  assign special_flags_d[`DP_SP_POS_INF] = |positive_inf_sources;
  assign special_flags_d[`DP_SP_NEG_INF] = |negative_inf_sources;
  assign all_negative_d                  = &included_negative;
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s0_s1_product_negative (.clock(clock), .in_en(rst_n & in_valid), .in_d(product_negative_d), .out_q(out_product_negative));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s0_s1_product_active (.clock(clock), .in_en(rst_n & in_valid), .in_d(product_active_d), .out_q(out_product_active));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s0_s1_special_flags (.clock(clock), .in_en(rst_n & in_valid), .in_d(special_flags_d), .out_q(out_special));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s0_s1_all_negative (.clock(clock), .in_en(rst_n & in_valid), .in_d(all_negative_d), .out_q(out_all_negative));
  // verilog_format: on
endmodule
