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
module dp_global_align #(
  // v1.8 MAX 使用 S5 已寄存的 compare_exp，移位仍按原 anchor 计算。
  parameter integer PRECOMPUTED_EXPONENT = 0,
  parameter integer N = 5,
  parameter integer MAG_W = 39,
  parameter integer ANCHOR_W = 10,
  parameter integer Z_W = $clog2(MAG_W + 1)
) (
  input wire in_integer,
  input wire in_enable,
  input wire [N*MAG_W-1:0] in_magnitude,
  input wire [N*ANCHOR_W-1:0] in_anchor,
  input wire [N*ANCHOR_W-1:0] in_compare_exp,
  input wire [N*Z_W-1:0] in_z,
  input wire [N-1:0] in_negative,
  input wire [N*`DP_SPECIAL_W-1:0] in_special,
  output wire [N*(MAG_W+1)-1:0] out_leaves,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  output wire out_negative_zero,
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar source_index;

  `include "dp_functions.vh"
  localparam integer NET_W = ANCHOR_W + 1;
  wire [N*ANCHOR_W-1:0] exponents;
  wire [N-1:0] active;
  wire [N-1:0] negative_zero;
  wire any_active;
  wire [`DP_SPECIAL_W-1:0] special_comb;
  assign out_special = special_comb;
  // [S6 特殊旁带] 所有源分类归约；正负 Inf 同现置 invalid。
  // 特殊值不进入数值 MAX/移位，最终输出仍依旁带在 S8 选择，不能被零幅值屏蔽。
  wire [N-1:0] nan_sources;
  wire [N-1:0] invalid_sources;
  wire [N-1:0] positive_inf_sources;
  wire [N-1:0] negative_inf_sources;
  generate
    for (
      source_index = 0; source_index < N; source_index = source_index + 1
    ) begin : g_special_reduce
      assign nan_sources[source_index] = 1'b1 & in_special[source_index*`DP_SPECIAL_W+`DP_SP_NAN];
      assign invalid_sources[source_index] = 1'b1 &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_INVALID];
      assign positive_inf_sources[source_index] = 1'b1 &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_POS_INF];
      assign negative_inf_sources[source_index] = 1'b1 &
        in_special[source_index*`DP_SPECIAL_W+`DP_SP_NEG_INF];
    end
  endgenerate
  assign special_comb[`DP_SP_NAN] = |nan_sources;
  assign special_comb[`DP_SP_POS_INF] = |positive_inf_sources;
  assign special_comb[`DP_SP_NEG_INF] = |negative_inf_sources;
  assign special_comb[`DP_SP_INVALID] = (|invalid_sources) |
    ((|positive_inf_sources) & (|negative_inf_sources));
  // [S6 共同坐标] v1.8 直接比较 S5 compare_exp；legacy 在这里计算 A_raw-z。
  // C 的 compare_exp 可以是非正规数真实指数的上界，不要求 MAX 源最高位为1。
  // 输入幅值已由 top 静态补零到共同 MAG_W；符号独立，C 与 group 同等参与。
  dp_max_tree #(
    .N(N),
    .W(ANCHOR_W)
  ) u_global_anchor_max (
    .in_values(exponents),
    .in_active(active),
    .out_max(out_anchor),
    .out_active(any_active)
  );
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
      assign net_shift = $signed(
        {raw_anchor[ANCHOR_W-1], raw_anchor}
      ) - $signed(
        {out_anchor[ANCHOR_W-1], out_anchor}
      );
      wire [MAG_W-1:0] isolated_magnitude;
      assign isolated_magnitude = active[source_index] ? magnitude : 0;
      wire [MAG_W-1:0] shifted;
      wire [MAG_W-1:0] result_magnitude;
      assign result_magnitude = in_integer ? magnitude : shifted;
      assign active[source_index] = in_enable & ~in_integer & magnitude != 0 &
        in_special[source_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] == 0;
      assign exponents[source_index*ANCHOR_W+:ANCHOR_W] = (PRECOMPUTED_EXPONENT != 0) ?
        in_compare_exp[source_index*ANCHOR_W+:ANCHOR_W] : raw_anchor - $signed(
        {{(ANCHOR_W - Z_W) {1'b0}}, leading}
      );
      dp_bidir_shift #(
        .W(MAG_W),
        .NET_W(NET_W)
      ) u_global_align_shift (
        .in_magnitude(isolated_magnitude),
        .in_net(net_shift),
        .out_magnitude(shifted)
      );
      // [恢复补码] 幅值移位结束后再加符号位并取负，供 S7 补码累加树使用。
      // 负零单独保留；仅当所有叶子都为负零且总和为零时，最终结果选择负零。
      assign out_leaves[source_index*(MAG_W+1)+:MAG_W+1] = in_negative[source_index] ? -$signed(
        {1'b0, result_magnitude}
      ) : $signed(
        {1'b0, result_magnitude}
      );
      assign negative_zero[source_index] = in_negative[source_index] & result_magnitude == 0;
    end
  endgenerate
  assign out_negative_zero = &negative_zero;
endmodule
