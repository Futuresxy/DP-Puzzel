`include "dp_defs.vh"
// 多精度 lane 的完整 S3 局部对齐：S2 乘积/公共 anchor -> S3 补码叶子。
// 纯组合，无 clock/reset/内部寄存器；dp_lane 在 ff_s2_s3_leaves 保存输出。
// in_valid=0 时所有叶子为零。datatype/active/negative 必须属于同一笔 S2 数据。
// 计算顺序：E 两项先求和 -> 幅值落入 LOCAL_W 窗口 -> RTZ 右移 -> 恢复符号。
// T/H/Q 每路选一个乘积；E 每路选两个乘积；四路物理右移器被互斥格式复用。
// LOCAL_W 是无符号窗口，LEAF_W=LOCAL_W+1 增加补码符号位，不增加小数精度。
// P=LOCAL_W-2，I 不包含 S；下表为输出补码叶子，而非未对齐的原始乘积。
// Precision                 | S | I  | F
// ------------------------- | - | -- | ----
// TF32 / FP16 / BF16 / MXQ  | 1 | 2  | P
// MXFP4 / NVFP4             | 1 | 7  | P-5
// HiF4                      | 1 | 5  | P-3
// INT8                      | 1 | 15 | P-13
module dp_lane_align #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  parameter integer LEAF_W  = LOCAL_W + 1
) (
  input wire in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] in_products,
  input wire [`DP_E_LANES-1:0] in_negative,
  input wire [`DP_E_LANES-1:0] in_active,
  input wire [`DP_PRODUCT_EXP_W-1:0] in_anchor,
  input wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] in_exponents,
  output wire [`DP_Q_LANES*LEAF_W-1:0] out_leaves
);
  `include "dp_functions.vh"
  genvar pair_index;
  generate
    for (pair_index = 0; pair_index < `DP_Q_LANES; pair_index = pair_index + 1) begin : g_align
      wire [LOCAL_W-1:0] shift_input;
      wire [`DP_PRODUCT_EXP_W-1:0] delta;
      wire sign_value;
      wire signed [`DP_E_PAIR_W-1:0] pair_a;
      wire signed [`DP_E_PAIR_W-1:0] pair_b;
      wire signed [`DP_E_PAIR_W-1:0] pair_sum;
      wire [`DP_E_PAIR_W-1:0] pair_abs;
      wire [LOCAL_W-1:0] shifted;
      wire [`DP_PRODUCT_W-1:0] product_value;
      assign product_value = in_products[pair_index*`DP_PRODUCT_W+:`DP_PRODUCT_W];
      wire select_pair;
      wire select_element;
      wire select_float;
      wire [`DP_E_PAIR_W-1:0] pair_magnitude_a;
      wire [`DP_E_PAIR_W-1:0] pair_magnitude_b;
      assign select_pair = in_valid & (elements(in_datatype) == `DP_E_LANES);
      assign select_element = in_valid & ~select_pair & (pair_index < elements(in_datatype));
      assign select_float = select_element & (in_datatype != `DP_DT_INT8) & in_active[pair_index];
      assign pair_magnitude_a = in_products[(2*pair_index)*`DP_PRODUCT_W+:`DP_E_PAIR_W];
      assign pair_magnitude_b = in_products[(2*pair_index+1)*`DP_PRODUCT_W+:`DP_E_PAIR_W];
      // 1. E pair：先将两个幅值恢复补码再相加，保留抵消；之后重新分离符号。
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
      assign shift_input = select_pair ? {{(LOCAL_W - `DP_E_PAIR_W) {1'b0}}, pair_abs} <<
        (LEAF_W - `DP_E_PAIR_W) : (select_element & (in_datatype == `DP_DT_INT8)) ?
        {{(LOCAL_W - `DP_PRODUCT_W) {1'b0}}, product_value} << (LEAF_W - `DP_INT_PRODUCT_W) :
        select_float ?
        {{(LOCAL_W - `DP_PRODUCT_W) {1'b0}}, product_value} << (LOCAL_W - 2 - product_fraction(
        in_datatype
      )) : 0;
      // 3. 公共 anchor 由本 group 两个 lane 在 S2 共同求 MAX；差值应非负。
      // 零/特殊乘积不参加浮点 MAX；MX/NV pair 与 INT8 的右移量为零。
      assign delta = (select_pair & (in_datatype == `DP_DT_HIF4) & (pair_abs != 0)) ? in_anchor -
        in_exponents[(2*pair_index)*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] : select_float ?
        in_anchor - in_exponents[pair_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] : 0;
      // 4. 共享幅值右移：丢弃低位即 RTZ，不能对负补码直接做算术右移。
      dp_rtz_shift #(
        .W(LOCAL_W),
        .SHIFT_W(`DP_PRODUCT_EXP_W)
      ) u_local_align_shift (
        .in_magnitude(shift_input),
        .in_shift(delta),
        .out_magnitude(shifted)
      );
      // 5. 右移完成后才恢复补码，交给 S4 平衡累加树；符号未混入移位器。
      assign out_leaves[pair_index*LEAF_W+:LEAF_W] = sign_value ? -$signed(
        {1'b0, shifted}
      ) : $signed(
        {1'b0, shifted}
      );
    end
  endgenerate
endmodule
