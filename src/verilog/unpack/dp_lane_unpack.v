`include "dp_defs.vh"
// A/B 解包入口：两侧各保存 S1 M32/E20/S8，数值译码及特殊分类集中在 unpack 区域。
// S1 后按对应元素配对计算 0*Inf、sNaN 和 Inf 符号，归约为 4 位 lane 分类。
// 配对逻辑仍在原 S2 组合区；dp_lane 的 S2 DFF 捕获，无新增流水级。
// 输出符号保持 atom 紧凑槽；product_negative/active 是 S2 逐乘积掩码。
module dp_lane_unpack #(
  // Static format capability, not a runtime functional input.
  parameter integer QE_ONLY = 0,
  // 仅多精度 lane 启用分段寄存器门控；QE 原实现保持默认。
  parameter integer PRECISION_GATING = 0
) (
  // 上升沿流水时钟。
  // verilog_format: off
  input wire                          clock,
  // 同步低有效复位；与 valid 共同屏蔽 payload 捕获。
  input wire                          rst_n,
  // 当前请求有效，S1 payload 仅在有效且不复位时更新。
  input wire                          in_valid,
  // 当前输入格式；按该格式完成 S1 译码。
  input wire [`DP_TYPE_W-1:0]         in_datatype,
  // 与 S1 字段同拍保存的格式，用于 S2 分类槽选择。
  input wire [`DP_TYPE_W-1:0]         in_registered_datatype,
  // A 原始 32 位 lane 输入。
  input wire [`DP_LANE_W-1:0]         in_a,
  // B 原始 32 位 lane 输入，与 A 对应元素配对。
  input wire [`DP_LANE_W-1:0]         in_b,
  // A 的 HiF4 e1 元数据，每四个元素共用一位。
  input wire [1:0]                    in_e1_a,
  // B 的 HiF4 e1 元数据，每四个元素共用一位。
  input wire [1:0]                    in_e1_b,
  // A 的 HiF4 e2 元数据，八个元素共享。
  input wire                          in_e2_a,
  // B 的 HiF4 e2 元数据，八个元素共享。
  input wire                          in_e2_b,
  // A 的 S1 紧凑 M32，两个 M16 atom；幅值格式见元素解码器 S/I/F 表。
  output wire [`DP_UNPACK_MANT_W-1:0] out_a_mantissas,
  // B 的 S1 紧凑 M32，与 A 使用相同字段布局。
  output wire [`DP_UNPACK_MANT_W-1:0] out_b_mantissas,
  // A 的 S1 紧凑 E20，两个 E10 atom；不能作为单个整数指数相加。
  output wire [`DP_UNPACK_EXP_W-1:0]  out_a_exponents,
  // B 的 S1 紧凑 E20，指数 bank 按格式选择字段。
  output wire [`DP_UNPACK_EXP_W-1:0]  out_b_exponents,
  // A 的 S1 紧凑 S8，每 atom 四槽；未用槽为零。
  output wire [`DP_UNPACK_SIGN_W-1:0] out_a_signs,
  // B 的 S1 紧凑 S8，每 atom 四槽；保留负零符号。
  output wire [`DP_UNPACK_SIGN_W-1:0] out_b_signs,
  // S2 逐乘积符号，A/B 符号 XOR；未用元素为零。
  output wire [`DP_E_LANES-1:0]       out_product_negative,
  // S2 有限非零乘积掩码，供指数 MAX 屏蔽零和特殊值。
  output wire [`DP_E_LANES-1:0]       out_product_active,
  // S2 lane 分类摘要：NaN、invalid、正 Inf、负 Inf。
  output wire [`DP_SPECIAL_W-1:0]     out_special,
  // 全部参与项的乘积符号均为负；包含零乘积，供最终零符号选择。
  output wire                         out_all_negative
  // verilog_format: on
);
  `include "dp_functions.vh"
  // A/B 的 S1 分类保留元素位置；不能先把 Inf/Zero 各自 OR 后再判断乘法。
  // verilog_format: off
  wire [`DP_UNPACK_CLASS_W-1:0] r1_a_classes;
  // B 子模块保存的 S1 分类，与 A 同布局。
  wire [`DP_UNPACK_CLASS_W-1:0] r1_b_classes;
  // A 子模块保存的 S1 sNaN 槽。
  wire [`DP_UNPACK_SIGN_W-1:0]  r1_a_signaling;
  // B 子模块保存的 S1 sNaN 槽。
  wire [`DP_UNPACK_SIGN_W-1:0]  r1_b_signaling;
  // verilog_format: on

  dp_lane_operand_unpack #(.QE_ONLY(QE_ONLY), .PRECISION_GATING(PRECISION_GATING)) u_operand_a (
    .clock        (clock),
    .rst_n        (rst_n),
    .in_valid     (in_valid),
    .in_datatype  (in_datatype),
    .in_registered_datatype(in_registered_datatype),
    .in_data      (in_a),
    .in_e1        (in_e1_a),
    .in_e2        (in_e2_a),
    .out_mantissas(out_a_mantissas),
    .out_exponents(out_a_exponents),
    .out_signs    (out_a_signs),
    .out_classes  (r1_a_classes),
    .out_signaling(r1_a_signaling)
  );

  dp_lane_operand_unpack #(.QE_ONLY(QE_ONLY), .PRECISION_GATING(PRECISION_GATING)) u_operand_b (
    .clock        (clock),
    .rst_n        (rst_n),
    .in_valid     (in_valid),
    .in_datatype  (in_datatype),
    .in_registered_datatype(in_registered_datatype),
    .in_data      (in_b),
    .in_e1        (in_e1_b),
    .in_e2        (in_e2_b),
    .out_mantissas(out_b_mantissas),
    .out_exponents(out_b_exponents),
    .out_signs    (out_b_signs),
    .out_classes  (r1_b_classes),
    .out_signaling(r1_b_signaling)
  );

  // S2 仅路由分类槽，不重新读取原始浮点编码或生成宽 Number。
  // verilog_format: off
  wire select_h;
  // E 格式字段选择，每 atom 四项。
  wire select_e;
  assign select_h = (QE_ONLY == 0) & ((in_registered_datatype == `DP_DT_TF32) | (in_registered_datatype == `DP_DT_FP16) | (in_registered_datatype == `DP_DT_BF16));
  assign select_e = (in_registered_datatype == `DP_DT_MXFP4) | (in_registered_datatype == `DP_DT_NVFP4) | (in_registered_datatype == `DP_DT_HIF4);
  // verilog_format: on

  // 分类归约掩码；all_negative 包含零乘积，未用槽为归约与的 1。
  // verilog_format: off
  wire [`DP_E_LANES-1:0] nan_sources;
  // 参与归约的逐乘积 sNaN 或 0*Inf 标志。
  wire [`DP_E_LANES-1:0] invalid_sources;
  // 参与归约的逐乘积正 Inf 标志。
  wire [`DP_E_LANES-1:0] positive_inf_sources;
  // 参与归约的逐乘积负 Inf 标志。
  wire [`DP_E_LANES-1:0] negative_inf_sources;
  // 参与项取乘积符号；未用项置 1，作为归约与的单位元。
  wire [`DP_E_LANES-1:0] included_negative;
  // verilog_format: on
  // 生成期元素索引，不是运行时计数器。
  genvar element_index;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_pair_class
      // H/Q/E 每 atom 分别使用 1/2/4 个槽，以下索引在 elaboration 时确定。
      localparam integer H_SLOT = (element_index % `DP_LANES) * `DP_UNPACK_ATOM_SIGN_W;
      // Q/INT8 元素对应的紧凑槽，每 atom 使用槽 0/1。
      localparam integer Q_SLOT = ((element_index / `DP_UNPACK_ATOM_Q_LANES) % `DP_LANES) *
        `DP_UNPACK_ATOM_SIGN_W + element_index % `DP_UNPACK_ATOM_Q_LANES;
      // E 元素对应的紧凑槽，与连续元素编号一致。
      localparam integer E_SLOT = element_index;
      // 当前元素是否属于已寄存格式的有效容量。
      // verilog_format: off
      wire                       element_used;
      // 按 H/Q/E 槽映射选出的 A 分类。
      wire [`DP_NUM_CLASS_W-1:0] a_class;
      // 按相同槽映射选出的 B 分类。
      wire [`DP_NUM_CLASS_W-1:0] b_class;
      // 当前 A 元素符号，包含负零。
      wire                       a_sign;
      // 当前 B 元素符号，包含负零。
      wire                       b_sign;
      // 当前 A 元素的 sNaN 标志。
      wire                       a_signaling;
      // 当前 B 元素的 sNaN 标志。
      wire                       b_signaling;
      assign element_used = element_index < ((QE_ONLY != 0) ? (select_e ? `DP_E_LANES : `DP_Q_LANES) : elements(in_registered_datatype));
      assign a_class      = select_h ? r1_a_classes[H_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] :
                            select_e ? r1_a_classes[E_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] :
                                       r1_a_classes[Q_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
      assign a_sign       = select_h ? out_a_signs[H_SLOT] :
                            select_e ? out_a_signs[E_SLOT] :
                                       out_a_signs[Q_SLOT];
      assign a_signaling  = select_h ? r1_a_signaling[H_SLOT] :
                            select_e ? r1_a_signaling[E_SLOT] :
                                       r1_a_signaling[Q_SLOT];
      assign b_class      = select_h ? r1_b_classes[H_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] :
                            select_e ? r1_b_classes[E_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] :
                                       r1_b_classes[Q_SLOT*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
      assign b_sign       = select_h ? out_b_signs[H_SLOT] :
                            select_e ? out_b_signs[E_SLOT] :
                                       out_b_signs[Q_SLOT];
      assign b_signaling  = select_h ? r1_b_signaling[H_SLOT] :
                            select_e ? r1_b_signaling[E_SLOT] :
                                       r1_b_signaling[Q_SLOT];
      // verilog_format: on
      // 先配对再归约：NaN 不能当零；0*Inf 是 invalid；Inf 符号由 A/B XOR 决定。
      // verilog_format: off
      wire pair_nan;
      // 本元素 A/B 至少一侧为 Inf。
      wire pair_inf;
      // 本元素 A/B 至少一侧为零；不能与其他元素交叉配对。
      wire pair_zero;
      // 有效 Inf 乘积，排除 NaN 和 0*Inf。
      wire pair_infinity;
      assign pair_nan                            = (a_class == `DP_CLASS_NAN) | (b_class == `DP_CLASS_NAN);
      assign pair_inf                            = (a_class == `DP_CLASS_INF) | (b_class == `DP_CLASS_INF);
      assign pair_zero                           = (a_class == `DP_CLASS_ZERO) | (b_class == `DP_CLASS_ZERO);
      assign pair_infinity                       = element_used & pair_inf & ~pair_zero & ~pair_nan;
      assign out_product_negative[element_index] = element_used & (a_sign ^ b_sign);
      assign out_product_active[element_index]   = element_used & (a_class == `DP_CLASS_FINITE) & (b_class == `DP_CLASS_FINITE);
      assign nan_sources[element_index]          = element_used & pair_nan;
      assign invalid_sources[element_index]      = element_used & (a_signaling | b_signaling | (pair_inf & pair_zero));
      assign positive_inf_sources[element_index] = pair_infinity & ~out_product_negative[element_index];
      assign negative_inf_sources[element_index] = pair_infinity & out_product_negative[element_index];
      assign included_negative[element_index]    = ~element_used | out_product_negative[element_index];
      // verilog_format: on
    end
  endgenerate
  // lane 分类只输出四位；与旧 special 位语义一致，不是外部异常状态寄存器。
  // verilog_format: off
  assign out_special[`DP_SP_NAN]     = |nan_sources;
  assign out_special[`DP_SP_POS_INF] = |positive_inf_sources;
  assign out_special[`DP_SP_NEG_INF] = |negative_inf_sources;
  assign out_special[`DP_SP_INVALID] = (|invalid_sources) | ((|positive_inf_sources) & (|negative_inf_sources));
  assign out_all_negative            = &included_negative;
  // verilog_format: on
endmodule
