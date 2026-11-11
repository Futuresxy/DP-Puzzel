`include "dp_defs.vh"
// 多精度 lane 的完整 S3 局部对齐：S2 乘积/公共 anchor -> S3 补码叶子。
// 纯组合，无 clock/reset/内部寄存器；dp_lane 在 ff_s2_s3_leaves 保存输出。
// in_valid=0 时所有叶子为零。datatype/active/negative 必须属于同一笔 S2 数据。
// E_FIXED_COORD=1：E 两项补码求和后直接进入树，跳过宽右移；INT8 静态旁路。
// E_FIXED_COORD=0：保留旧 E pair -> abs/RTZ/符号恢复，用于未迁移顶层。
// T/H/Q 每路选一个乘积；E 每路选两个乘积；四路物理右移器被互斥格式复用。
// LOCAL_W 是无符号窗口，LEAF_W=LOCAL_W+1 增加补码符号位，不增加小数精度。
// P=LOCAL_W-2，I 不包含 S；下表为输出补码叶子，而非未对齐的原始乘积。
// Precision                 | S | I  | F
// ------------------------- | - | -- | ----
// TF32 / FP16 / BF16 / MXQ  | 1 | 2  | P
// MXFP4 / NVFP4             | 1 | 7  | P-5
// HiF4 legacy              | 1 | 5  | P-3
// v1.8 MX/NV pair           | 1 | 9  | P-7
// v1.8 HiF4 pair            | 1 | 7  | P-5
// INT8                      | 1 | 15 | P-13
module dp_lane_align #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  parameter integer LEAF_W  = LOCAL_W + 1,
  // Static QE pruning and natural S2 slot widths.
  parameter integer QE_ONLY = 0,
  // v1.8 E pair 直接输出补码、隔离宽移位；其余调用者保留旧模式。
  parameter integer E_FIXED_COORD = 0,
  parameter integer PRODUCT_W = `DP_PRODUCT_W,
  parameter integer EXPONENT_W = `DP_PRODUCT_EXP_W
) (
  input wire in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_E_LANES*PRODUCT_W-1:0] in_products,
  input wire [`DP_E_LANES-1:0] in_negative,
  input wire [`DP_E_LANES-1:0] in_active,
  input wire [EXPONENT_W-1:0] in_anchor,
  input wire [`DP_E_LANES*EXPONENT_W-1:0] in_exponents,
  output wire [`DP_Q_LANES*LEAF_W-1:0] out_leaves
);
  `include "dp_functions.vh"
  genvar pair_index;
  generate
    for (pair_index = 0; pair_index < `DP_Q_LANES; pair_index = pair_index + 1) begin : g_align
      wire [LOCAL_W-1:0] shift_input;
      wire [EXPONENT_W-1:0] delta;
      wire sign_value;
      wire signed [`DP_E_PAIR_W-1:0] pair_a;
      wire signed [`DP_E_PAIR_W-1:0] pair_b;
      wire signed [`DP_E_PAIR_W-1:0] pair_sum;
      wire [`DP_E_PAIR_W-1:0] pair_abs;
      wire [LOCAL_W-1:0] shifted;
      wire [PRODUCT_W-1:0] product_value;
      assign product_value = in_products[pair_index*PRODUCT_W+:PRODUCT_W];
      wire select_pair;
      wire select_element;
      wire select_float;
      wire [`DP_E_PAIR_W-1:0] pair_magnitude_a;
      wire [`DP_E_PAIR_W-1:0] pair_magnitude_b;
      assign select_pair = in_valid & (((QE_ONLY != 0) ? (((in_datatype >= `DP_DT_MXFP4) & (in_datatype <= `DP_DT_HIF4)) ? `DP_E_LANES : `DP_Q_LANES) : elements(in_datatype)) == `DP_E_LANES);
      assign select_element = in_valid & ~select_pair & (pair_index < ((QE_ONLY != 0) ? (((in_datatype >= `DP_DT_MXFP4) & (in_datatype <= `DP_DT_HIF4)) ? `DP_E_LANES : `DP_Q_LANES) : elements(in_datatype)));
      assign select_float = select_element & (in_datatype != `DP_DT_INT8) & in_active[pair_index];
      assign pair_magnitude_a = {{(`DP_E_PAIR_W-2*`DP_EIGHTH_W){1'b0}}, in_products[(2*pair_index)*PRODUCT_W+:2*`DP_EIGHTH_W]};
      assign pair_magnitude_b = {{(`DP_E_PAIR_W-2*`DP_EIGHTH_W){1'b0}}, in_products[(2*pair_index+1)*PRODUCT_W+:2*`DP_EIGHTH_W]};
      // 1. E pair：两个幅值符号化后相加，保留抵消；v1.8 直接使用 pair_sum。
      // pair 容器含增长位，合法 E 乘积和不溢出。其他格式不启用此支路。
      assign pair_a = select_pair ?
        (in_negative[2*pair_index] ? -pair_magnitude_a : pair_magnitude_a) : 0;
      assign pair_b = select_pair ?
        (in_negative[2*pair_index+1] ? -pair_magnitude_b : pair_magnitude_b) : 0;
      assign pair_sum = pair_a + pair_b;
      assign pair_abs = pair_sum[`DP_E_PAIR_W-1] ? -pair_sum : pair_sum;
      assign sign_value = select_pair ? pair_sum[`DP_E_PAIR_W-1] :
        select_element & in_negative[pair_index];
      // 2. 按格式将幅值放入共享窗口：低补零用于坐标匹配，不创造有效精度。
      // HiF4 pair 的 guard zeros 保证后续 e2 差值 0..2 的右移不损失数值。
      // INT8 只做静态落位；T/H/Q 依 product_fraction 确定二进制点。
      assign shift_input = ((E_FIXED_COORD != 0) & (select_pair | (in_datatype == `DP_DT_INT8))) ? 0 : select_pair ? {{(LOCAL_W - `DP_E_PAIR_W) {1'b0}}, pair_abs} <<
        (LEAF_W - `DP_E_PAIR_W) : (select_element & ((QE_ONLY == 0) & (in_datatype == `DP_DT_INT8))) ?
        {{(LOCAL_W - PRODUCT_W) {1'b0}}, product_value} << (LEAF_W - `DP_INT_PRODUCT_W) :
        select_float ?
        {{(LOCAL_W - PRODUCT_W) {1'b0}}, product_value} << (LOCAL_W - 2 - ((QE_ONLY != 0) ? (2 * `DP_SCALE_F) : product_fraction(in_datatype))) : 0;
      // 3. 公共 anchor 由本 group 两个 lane 在 S2 共同求 MAX；差值应非负。
      // 零/特殊乘积不参加浮点 MAX；MX/NV pair 与 INT8 的右移量为零。
      assign delta = ((E_FIXED_COORD == 0) & select_pair & (in_datatype == `DP_DT_HIF4) & (pair_abs != 0)) ? in_anchor -
        in_exponents[(2*pair_index)*EXPONENT_W+:EXPONENT_W] : select_float ?
        in_anchor - in_exponents[pair_index*EXPONENT_W+:EXPONENT_W] : 0;
      // 4. 共享幅值右移：丢弃低位即 RTZ，不能对负补码直接做算术右移。
      dp_rtz_shift #(
        .W(LOCAL_W),
        .SHIFT_W(EXPONENT_W)
      ) u_local_align_shift (
        .in_magnitude(shift_input),
        .in_shift(delta),
        .out_magnitude(shifted)
      );
      // 5. 右移完成后才恢复补码，交给 S4 平衡累加树；符号未混入移位器。
      // v1.8 E signed pair 低补零并预留两位 e2 增长空间；不再 abs/右移/再符号化。
      // INT8 直接静态落位；两条旁路将宽右移器输入置零以抑制无效活动。
      wire signed [LEAF_W-1:0] pair_leaf;
      wire [LEAF_W-1:0] integer_magnitude;
      wire signed [LEAF_W-1:0] integer_leaf;
      assign pair_leaf = { {`DP_E_GUARD{pair_sum[`DP_E_PAIR_W-1]}}, pair_sum,
                           {(LEAF_W-`DP_E_PAIR_W-`DP_E_GUARD){1'b0}} };
      assign integer_magnitude = {{(LEAF_W-PRODUCT_W){1'b0}}, product_value} << (LEAF_W-`DP_INT_PRODUCT_W);
      assign integer_leaf = select_element ? (sign_value ? -$signed(integer_magnitude) : $signed(integer_magnitude)) : 0;
      assign out_leaves[pair_index*LEAF_W+:LEAF_W] =
          ((E_FIXED_COORD != 0) & select_pair) ? pair_leaf :
          ((E_FIXED_COORD != 0) & (in_datatype == `DP_DT_INT8)) ? integer_leaf :
          sign_value ? -$signed({1'b0, shifted}) : $signed({1'b0, shifted});
    end
  endgenerate
endmodule
