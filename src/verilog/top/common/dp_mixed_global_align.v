`include "dp_defs.vh"
// S6 combinational MAX/one bidirectional shift per source/sign restoration.
// Inputs are statically padded to MAG_W. A_raw already includes each source F.
// Float padding keeps I and adds MAG_W-M_src to F; A_raw sets its coordinate.
// S6 unsigned magnitude -> TC tree leaf. Both use the listed I/F.
// Precision          | Mag S | Leaf S | I  | F
// ------------------ | ----- | ------ | -- | --------
// All floating modes | 0     | 1      | 1  | MAG_W-1
// INT8 + INT32       | 0     | 1      | 32 | MAG_W-32
// Floating coordinates use E_max; INT8+INT32 bypasses the shift.
module dp_mixed_global_align #(
  // S5 已寄存真实最高位指数；0 仅供 legacy 接口回放。
  parameter integer PRECOMPUTED_COMPARE = 0,
  // 静态能力裁剪；仅扩展组可裁掉整数直通，基础组和 C 仍支持整数。
  parameter integer FLOAT_ONLY_EXTENSION = 0,
  // Four base groups and one C, plus the enabled low-precision branch.
  parameter integer BASE_GROUPS = 4,
  // 新增低精度 group 数量，E96 为 2，E128/Q64E128 为 4。
  parameter integer EXT_GROUPS = 2,
  // 参与公共后端的物理源数：所有 group 加一次 C。
  parameter integer N = BASE_GROUPS + EXT_GROUPS + 1,
  // 符号分离后的幅值位宽，不含符号。
  parameter integer MAG_W = 39,
  // 有符号指数坐标宽度，由合法幅值窗口推导。
  parameter integer ANCHOR_W = 10,
  parameter integer Z_W = $clog2(MAG_W + 1)
) (
  // Request-aligned group membership, with C always participating.
  input wire [N-1:0] in_participate,
  // INT8/INT32 模式选择，此时绕过浮点对齐。
  input wire in_integer,
  // S5 有效控制，屏蔽气泡期间的组合移位活动。
  input wire in_enable,
  // 已由顶层低位补零到共同 MAG_W 的每源幅值。
  input wire [N*MAG_W-1:0] in_magnitude,
  // 每源有符号 A_raw 指数坐标。
  input wire [N*ANCHOR_W-1:0] in_anchor,
  input wire [N*ANCHOR_W-1:0] in_compare_exp,
  // 每源原幅值前导零数；低位补零不改变非零源 z。
  input wire [N*Z_W-1:0] in_z,
  // 每源独立符号位。
  input wire [N-1:0] in_negative,
  // 每源四位分类标志，屏蔽关闭源后参与归约。
  input wire [N*`DP_SPECIAL_W-1:0] in_special,
  // 移位后恢复为补码的各源叶子，供 S7 规约。
  output wire [N*(MAG_W+1)-1:0] out_leaves,
  // S5 token 原始指数坐标 A_raw，真实最高位指数为 A_raw-z。
  output wire signed [ANCHOR_W-1:0] out_anchor,
  // 所有参与叶子均为负零的归约标志。
  output wire out_negative_zero,
  // NaN/invalid/正 Inf/负 Inf 的独立分类摘要。
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar source_index;

  `include "dp_functions.vh"
  // 双向净移位量的有符号宽度，多一位防止差值溢出。
  localparam integer NET_W = ANCHOR_W + 1;
  wire [N*ANCHOR_W-1:0] exponents;
  wire [N-1:0] active;
  wire [N-1:0] negative_zero;
  // Independent base/extension maxima, with empty branches represented by has_value.
  wire base_active;
  wire extension_active;
  wire signed [ANCHOR_W-1:0] base_max;
  wire signed [ANCHOR_W-1:0] extension_max;
  wire [`DP_SPECIAL_W-1:0] special_comb;
  assign out_special = special_comb;
  // [S6 特殊旁带] 所有源分类归约；正负 Inf 同现置 invalid。
  // 特殊值不进入数值 MAX/移位，最终输出仍依旁带在 S8 选择，不能被零幅值屏蔽。
  wire [N-1:0] nan_sources;
  wire [N-1:0] invalid_sources;
  wire [N-1:0] positive_inf_sources;
  wire [N-1:0] negative_inf_sources;
  generate
    for (source_index = 0; source_index < N; source_index = source_index + 1) begin : g_special_reduce
      assign nan_sources[source_index] = in_participate[source_index] & in_special[source_index*`DP_SPECIAL_W+`DP_SP_NAN];
      assign invalid_sources[source_index] = in_participate[source_index] &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_INVALID];
      assign positive_inf_sources[source_index] = in_participate[source_index] &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_POS_INF];
      assign negative_inf_sources[source_index] = in_participate[source_index] &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_NEG_INF];
    end
  endgenerate
  assign special_comb[`DP_SP_NAN]     = |nan_sources;
  assign special_comb[`DP_SP_POS_INF] = |positive_inf_sources;
  assign special_comb[`DP_SP_NEG_INF] = |negative_inf_sources;
  assign special_comb[`DP_SP_INVALID] = (|invalid_sources) | ((|positive_inf_sources) & (|negative_inf_sources));
  // [S6 共同坐标] 对有限非零源计算 e=A_raw-z，并取 signed E_max。
  // 输入幅值已由 top 静态补零到共同 MAG_W；符号独立，C 与 group 同等参与。
  dp_max_tree #(
      .N(BASE_GROUPS + 1),
      .W(ANCHOR_W)
  ) u_base_max (
      .in_values ({exponents[(N-1)*ANCHOR_W+:ANCHOR_W], exponents[0+:BASE_GROUPS*ANCHOR_W]}),
      .in_active ({active[N-1], active[0+:BASE_GROUPS]}),
      .out_max   (base_max),
      .out_active(base_active)
  );
  dp_max_tree #(
      .N(EXT_GROUPS),
      .W(ANCHOR_W)
  ) u_extension_max (
      .in_values (exponents[BASE_GROUPS*ANCHOR_W+:EXT_GROUPS*ANCHOR_W]),
      .in_active (active[BASE_GROUPS+:EXT_GROUPS]),
      .out_max   (extension_max),
      .out_active(extension_active)
  );
  // Empty extension is a direct base bypass. Signed comparison preserves negative exponents.
  assign out_anchor = ~extension_active ? base_max : ~base_active ? extension_max :
                      (base_max >= extension_max) ? base_max : extension_max;
  generate
    for (source_index = 0; source_index < N; source_index = source_index + 1) begin : g_source
      wire signed [ANCHOR_W-1:0] raw_anchor;
      assign raw_anchor = in_anchor[source_index*ANCHOR_W+:ANCHOR_W];
      wire [Z_W-1:0] leading;
      assign leading = in_z[source_index*Z_W+:Z_W];
      wire [MAG_W-1:0] magnitude;
      assign magnitude = in_magnitude[source_index*MAG_W+:MAG_W];
      // [净移位] d=E_max-(A_raw-z)，所以 net=z-d=A_raw-E_max。
      // 一次双向移位同时完成规格化和组间对齐；NET_W 多一位防止有符号差溢出。
      wire signed [NET_W-1:0] net_shift;
      assign net_shift = ~active[source_index] ? 0 : $signed(
          {raw_anchor[ANCHOR_W-1], raw_anchor}
      ) - $signed(
          {out_anchor[ANCHOR_W-1], out_anchor}
      );
      wire [MAG_W-1:0] isolated_magnitude;
      assign isolated_magnitude = active[source_index] ? magnitude : 0;
      wire [MAG_W-1:0] shifted;
      wire [MAG_W-1:0] result_magnitude;
      // 参与资格保证扩展源只处理浮点；C 的索引在扩展组范围之外。
      if ((FLOAT_ONLY_EXTENSION != 0) & (source_index >= BASE_GROUPS) &
          (source_index < BASE_GROUPS + EXT_GROUPS)) begin : g_float_extension
        assign result_magnitude = in_participate[source_index] ? shifted : {MAG_W{1'b0}};
        assign active[source_index] = in_enable & in_participate[source_index] &
            (magnitude != 0) & (in_special[source_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] == 0);
      end else begin : g_integer_capable
        assign result_magnitude = ~in_participate[source_index] ? {MAG_W{1'b0}} : in_integer ? magnitude : shifted;
        assign active[source_index] = in_enable & in_participate[source_index] & ~in_integer &
            (magnitude != 0) & (in_special[source_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] == 0);
      end
      assign exponents[source_index*ANCHOR_W+:ANCHOR_W] = (PRECOMPUTED_COMPARE != 0) ? in_compare_exp[source_index*ANCHOR_W+:ANCHOR_W] : raw_anchor - $signed({{(ANCHOR_W - Z_W) {1'b0}}, leading});
      dp_bidir_shift #(
          .W    (MAG_W),
          .NET_W(NET_W)
      ) u_global_align_shift (
          .in_magnitude (isolated_magnitude),
          .in_net       (net_shift),
          .out_magnitude(shifted)
      );
      // [恢复补码] 幅值移位结束后再加符号位并取负，供 S7 补码累加树使用。
      // 负零单独保留；仅当所有叶子都为负零且总和为零时，最终结果选择负零。
      assign out_leaves[source_index*(MAG_W+1)+:MAG_W+1] = in_negative[source_index] ? -$signed(
          {1'b0, result_magnitude}
      ) : $signed(
          {1'b0, result_magnitude}
      );
      assign negative_zero[source_index] = ~in_participate[source_index] | (in_negative[source_index] & (result_magnitude == 0));
    end
  endgenerate
  assign out_negative_zero = &negative_zero;
endmodule
