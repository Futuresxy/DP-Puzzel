`include "dp_defs.vh"
// T1H2Q4E8. Owns S1 unpack, S2 products, S3 shared magnitude alignment,
// S4 lane tree. Common group MAX is a combinational S2 side interface.
// Synchronous low reset clears valid only; invalid data registers hold.
// P=LOCAL_W-2 (default 26). I excludes S; SM carries S separately.
// S3 shift magnitude -> TC tree leaf. Both use the listed I/F.
// Precision                    | Shift S | Leaf S | I  | F
// ---------------------------- | ------- | ------ | -- | ----
// TF32 / FP16 / BF16 / MXFP8/6 | 0       | 1      | 2  | P
// MXFP4 / NVFP4                | 0       | 1      | 7  | P-5
// HiF4                         | 0       | 1      | 5  | P-3
// INT8                         | 0       | 1      | 15 | P-13
// S3 E pair before guard/padding (TC, W10).
// Precision / signal | S | I | F
// ------------------ | - | - | -
// MXFP4 / NVFP4      | 1 | 7 | 2
// HiF4               | 1 | 5 | 4
// S4 lane SOP (TC).
// Precision / signal | S | I  | F
// ------------------ | - | -- | ----
// TF32               | 1 | 2  | P+2
// FP16 / BF16        | 1 | 3  | P+1
// MXFP8 / MXFP6      | 1 | 4  | P
// MXFP4 / NVFP4      | 1 | 9  | P-5
// HiF4               | 1 | 7  | P-3
// INT8               | 1 | 17 | P-13
// TF32/FP16/BF16 append 2/1/1 low zeros after the tree.
// 阅读顺序 / 功能边界：
// S1 u_operand_unpack_a/b 保存复用解包字段。
// S2 u_mantissa_mul_bank 产生幅值产品，u_exponent_add/MAX 同时准备对齐坐标。
// S3 u_local_alignment 完成 pair/落位/RTZ/符号恢复；S4 u_lane_sop_tree 规约。
// 末尾 ff_sN_sM_* 是这些组合区的捕获边界；valid_q[k] 对应 S(k+1)。
// 层内没有独立 ready；两 lane 的公共 MAX 在同拍组合完成，随产品一起进入 S2。
module dp_lane #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  parameter integer LEAF_W = LOCAL_W + 1,
  parameter integer LANE_SOP_W = LEAF_W + $clog2(`DP_Q_LANES)
) (
  input wire clock,
  input wire rst_n,
  input wire in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANE_W-1:0] in_a,
  input wire [`DP_LANE_W-1:0] in_b,
  input wire [1:0] in_e1_a,
  input wire [1:0] in_e1_b,
  input wire in_e2_a,
  input wire in_e2_b,
  output wire [`DP_PRODUCT_EXP_W-1:0] out_candidate,
  output wire out_candidate_active,
  input wire [`DP_PRODUCT_EXP_W-1:0] in_group_max,
  output wire out_valid,
  output wire signed [LANE_SOP_W-1:0] out_sop,
  output wire [`DP_PRODUCT_EXP_W-1:0] out_anchor,
  output wire [`DP_SPECIAL_W-1:0] out_special,
  output wire out_all_negative
);
  genvar element_index;

  `include "dp_functions.vh"
  wire [3:0] valid_q;
  wire [`DP_TYPE_W-1:0] type_s1_q;
  wire [`DP_TYPE_W-1:0] type_s2_q;
  wire [`DP_TYPE_W-1:0] type_s3_q;
  wire [`DP_E_LANES*`DP_NUM_W-1:0] unpack_a_lane_numbers;
  wire [`DP_E_LANES*`DP_NUM_W-1:0] unpack_b_lane_numbers;
  wire [`DP_E_LANES*`DP_MANT_W-1:0] lane_mantissa_mul_a_magnitude;
  wire [`DP_E_LANES*`DP_MANT_W-1:0] lane_mantissa_mul_b_magnitude;
  wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] products_d;
  wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] products_q;
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] exponents_d;
  wire [`DP_E_LANES*`DP_EXP_W-1:0] lane_exponent_add_a_exponents;
  wire [`DP_E_LANES*`DP_EXP_W-1:0] lane_exponent_add_b_exponents;
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] exponents_q;
  wire [`DP_E_LANES-1:0] negative_d;
  wire [`DP_E_LANES-1:0] active_d;
  wire [`DP_E_LANES-1:0] negative_q;
  wire [`DP_E_LANES-1:0] active_q;
  wire [`DP_E_LANES*`DP_SPECIAL_W-1:0] specials_d;
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] special_s2_q;
  wire [`DP_SPECIAL_W-1:0] special_s3_q;
  wire [`DP_SPECIAL_W-1:0] special_s4_q;
  wire all_negative_d;
  wire all_negative_s2_q;
  wire all_negative_s3_q;
  wire [`DP_PRODUCT_EXP_W-1:0] anchor_s2_q;
  wire [`DP_PRODUCT_EXP_W-1:0] anchor_s3_q;
  wire [`DP_Q_LANES*LEAF_W-1:0] leaves_d;
  wire [`DP_Q_LANES*LEAF_W-1:0] leaves_q;
  wire signed [LANE_SOP_W-1:0] lane_sum;
  assign out_valid   = valid_q[3];
  assign out_special = special_s4_q;
  // [S1 解包] A/B 各一份模块，内部拥有 S1 寄存器；展开的 Number 只是组合视图。
  // type_s1_q 与这些视图同拍，不能用当前输入 datatype 解释上一笔已寄存的 payload。
  dp_lane_unpack u_operand_unpack_a (
    .clock(clock),
    .rst_n(rst_n),
    .in_valid(in_valid),
    .in_datatype(in_datatype),
    .in_registered_datatype(type_s1_q),
    .in_data(in_a),
    .in_e1(in_e1_a),
    .in_e2(in_e2_a),
    .out_numbers(unpack_a_lane_numbers)
  );
  dp_lane_unpack u_operand_unpack_b (
    .clock(clock),
    .rst_n(rst_n),
    .in_valid(in_valid),
    .in_datatype(in_datatype),
    .in_registered_datatype(type_s1_q),
    .in_data(in_b),
    .in_e1(in_e1_b),
    .in_e2(in_e2_b),
    .out_numbers(unpack_b_lane_numbers)
  );
  // [S2 元素旁带] 从 Number 取幅值/指数，符号异或；分类信息独立于数值路径。
  // active 只包含当前格式的有限非零乘积，用于指数 MAX，不是整个事务的 valid。
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_element
      wire [`DP_NUM_W-1:0] a_q;
      wire [`DP_NUM_W-1:0] b_q;
      wire [`DP_SPECIAL_W-1:0] p_special;
      assign a_q = unpack_a_lane_numbers[element_index*`DP_NUM_W+:`DP_NUM_W];
      assign b_q = unpack_b_lane_numbers[element_index*`DP_NUM_W+:`DP_NUM_W];
      assign lane_mantissa_mul_a_magnitude[element_index*`DP_MANT_W+:`DP_MANT_W] =
        a_q[`DP_NUM_MAG_LO+:`DP_MANT_W];
      assign lane_mantissa_mul_b_magnitude[element_index*`DP_MANT_W+:`DP_MANT_W] =
        b_q[`DP_NUM_MAG_LO+:`DP_MANT_W];
      assign lane_exponent_add_a_exponents[element_index*`DP_EXP_W+:`DP_EXP_W] =
        a_q[`DP_NUM_EXP_LO+:`DP_EXP_W];
      assign lane_exponent_add_b_exponents[element_index*`DP_EXP_W+:`DP_EXP_W] =
        b_q[`DP_NUM_EXP_LO+:`DP_EXP_W];
      assign negative_d[element_index] = a_q[`DP_NUM_SIGN] ^ b_q[`DP_NUM_SIGN];
      assign p_special = product_special(a_q, b_q);
      assign specials_d[element_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] = p_special;
      assign active_d[element_index] = (a_q[`DP_NUM_MAG_LO+:`DP_MANT_W] != 0 &
                                        b_q[`DP_NUM_MAG_LO+:`DP_MANT_W] != 0 & p_special == 0 &
                                        element_index < elements(
        type_s1_q
      ));
    end
  endgenerate
  dp_exponent_bank u_exponent_add (
    .in_datatype(type_s1_q),
    .in_enable(valid_q[0]),
    .in_a(lane_exponent_add_a_exponents),
    .in_b(lane_exponent_add_b_exponents),
    .out_exponents(exponents_d)
  );
  // Exponent MAX does not depend on multiplier outputs or returned group MAX.
  wire [`DP_E_LANES*(`DP_PRODUCT_EXP_W+1)-1:0] max_candidates;
  wire signed [`DP_PRODUCT_EXP_W:0] lane_max;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_candidate
      assign max_candidates[element_index*(`DP_PRODUCT_EXP_W+1)+:`DP_PRODUCT_EXP_W+1] = {
        1'b0, exponents_d[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W]
      };
    end
  endgenerate
  dp_max_tree #(
    .N(`DP_E_LANES),
    .W(`DP_PRODUCT_EXP_W + 1)
  ) u_lane_exponent_max (
    .in_values(max_candidates),
    .in_active(active_d),
    .out_max(lane_max),
    .out_active(out_candidate_active)
  );
  assign out_candidate = lane_max[`DP_PRODUCT_EXP_W-1:0];
  // [S2 尾数乘法] bank 只计算无符号幅值；产品符号、指数、分类另行同拍寄存。
  dp_mantissa_bank u_mantissa_mul_bank (
    .in_datatype(type_s1_q),
    .in_enable(valid_q[0]),
    .in_a(lane_mantissa_mul_a_magnitude),
    .in_b(lane_mantissa_mul_b_magnitude),
    .out_products(products_d)
  );
  // [S2 特殊值与零符号] 聚合 NaN/Inf/invalid；正负 Inf 同时出现产生 invalid。
  // all_negative 包括零乘积，用于最终精确零的符号；不能只归约 active 产品。
  wire [`DP_E_LANES-1:0] included_negative;
  wire [`DP_E_LANES-1:0] nan_sources;
  wire [`DP_E_LANES-1:0] invalid_sources;
  wire [`DP_E_LANES-1:0] positive_inf_sources;
  wire [`DP_E_LANES-1:0] negative_inf_sources;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_special_reduce
      assign nan_sources[element_index] = (element_index < elements(
        type_s1_q
      )) & specials_d[element_index*`DP_SPECIAL_W+`DP_SP_NAN];
      assign invalid_sources[element_index] = (element_index < elements(
        type_s1_q
      )) & specials_d[element_index*`DP_SPECIAL_W+`DP_SP_INVALID];
      assign positive_inf_sources[element_index] = (element_index < elements(
        type_s1_q
      )) & specials_d[element_index*`DP_SPECIAL_W+`DP_SP_POS_INF];
      assign negative_inf_sources[element_index] = (element_index < elements(
        type_s1_q
      )) & specials_d[element_index*`DP_SPECIAL_W+`DP_SP_NEG_INF];
      assign included_negative[element_index] = (element_index >= elements(
        type_s1_q
      )) | negative_d[element_index];
    end
  endgenerate
  assign special_d[`DP_SP_NAN] = |nan_sources;
  assign special_d[`DP_SP_POS_INF] = |positive_inf_sources;
  assign special_d[`DP_SP_NEG_INF] = |negative_inf_sources;
  assign special_d[`DP_SP_INVALID] = (|invalid_sources) |
    ((|positive_inf_sources) & (|negative_inf_sources));
  assign all_negative_d = &included_negative;
  // [S3 局部对齐] 整个选择/pair/幅值移位/符号恢复由一个组合模块负责。
  // 输入是 S2 寄存器；输出在 ff_s2_s3_leaves 捕获，随后进入 S4 累加树。
  dp_lane_align #(
    .LOCAL_W(LOCAL_W),
    .LEAF_W (LEAF_W)
  ) u_local_alignment (
    .in_valid(valid_q[1]),
    .in_datatype(type_s2_q),
    .in_products(products_q),
    .in_negative(negative_q),
    .in_active(active_q),
    .in_anchor(anchor_s2_q),
    .in_exponents(exponents_q),
    .out_leaves(leaves_d)
  );
  // [S4 lane 累加树] 四个 S3 补码叶子平衡相加，每层增长一位，F 不变。
  // T/H 的低位静态补零在 S4 输出 DFF 输入完成，以统一 lane 容器坐标。
  dp_sum_tree #(
    .N(`DP_Q_LANES),
    .W(LEAF_W)
  ) u_lane_sop_tree (
    .in_values(leaves_q),
    .out_sum  (lane_sum)
  );

  // [流水保存] 下面按字段组织 DFF，不代表组合逻辑的执行先后。
  // valid 每拍推进；payload 在源级 valid 且 rst_n=1 时更新，bubble 保持旧数据。
  // S4 输出仅在 out_valid=1 时可解释；数据寄存器无需复位清零。
  // S0 -> S1: valid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s0_s1_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (in_valid),
    .out_q(valid_q[0])
  );
  // S1 -> S2: valid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s1_s2_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (valid_q[0]),
    .out_q(valid_q[1])
  );
  // S2 -> S3: valid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s2_s3_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (valid_q[1]),
    .out_q(valid_q[2])
  );
  // S3 -> S4: valid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s3_s4_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (valid_q[2]),
    .out_q(valid_q[3])
  );
  // S0 -> S1: type_s1.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s0_s1_type_s1 (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (in_datatype),
    .out_q(type_s1_q)
  );
  // S1 -> S2: products.
  dp_lib_DFFE #(
    .WIDTH(`DP_E_LANES * `DP_PRODUCT_W)
  ) ff_s1_s2_products (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (products_d),
    .out_q(products_q)
  );
  // S1 -> S2: exponents.
  dp_lib_DFFE #(
    .WIDTH(`DP_E_LANES * `DP_PRODUCT_EXP_W)
  ) ff_s1_s2_exponents (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (exponents_d),
    .out_q(exponents_q)
  );
  // S1 -> S2: negative.
  dp_lib_DFFE #(
    .WIDTH(`DP_E_LANES)
  ) ff_s1_s2_negative (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (negative_d),
    .out_q(negative_q)
  );
  // S1 -> S2: active.
  dp_lib_DFFE #(
    .WIDTH(`DP_E_LANES)
  ) ff_s1_s2_active (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (active_d),
    .out_q(active_q)
  );
  // S1 -> S2: anchor_s2.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s1_s2_anchor_s2 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (in_group_max),
    .out_q(anchor_s2_q)
  );
  // S1 -> S2: type_s2.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s1_s2_type_s2 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (type_s1_q),
    .out_q(type_s2_q)
  );
  // S1 -> S2: special_s2.
  dp_lib_DFFE #(
    .WIDTH(`DP_SPECIAL_W)
  ) ff_s1_s2_special_s2 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (special_d),
    .out_q(special_s2_q)
  );
  // S1 -> S2: all_negative_s2.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s1_s2_all_negative_s2 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (all_negative_d),
    .out_q(all_negative_s2_q)
  );
  // S2 -> S3: leaves.
  dp_lib_DFFE #(
    .WIDTH(`DP_Q_LANES * LEAF_W)
  ) ff_s2_s3_leaves (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (leaves_d),
    .out_q(leaves_q)
  );
  // S2 -> S3: anchor_s3.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s2_s3_anchor_s3 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (anchor_s2_q),
    .out_q(anchor_s3_q)
  );
  // S2 -> S3: type_s3.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s2_s3_type_s3 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (type_s2_q),
    .out_q(type_s3_q)
  );
  // S2 -> S3: special_s3.
  dp_lib_DFFE #(
    .WIDTH(`DP_SPECIAL_W)
  ) ff_s2_s3_special_s3 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (special_s2_q),
    .out_q(special_s3_q)
  );
  // S2 -> S3: all_negative_s3.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s2_s3_all_negative_s3 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (all_negative_s2_q),
    .out_q(all_negative_s3_q)
  );
  // S3 -> S4: out_sop.
  dp_lib_DFFE #(
    .WIDTH(LANE_SOP_W)
  ) ff_s3_s4_out_sop (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d(type_s3_q == `DP_DT_TF32 ? lane_sum << $clog2(
      `DP_Q_LANES
    ) : ((type_s3_q == `DP_DT_FP16) | (type_s3_q == `DP_DT_BF16)) ? lane_sum << ($clog2(
      `DP_Q_LANES
    ) - 1) : lane_sum),
    .out_q(out_sop)
  );
  // S3 -> S4: out_anchor.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s3_s4_out_anchor (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (anchor_s3_q),
    .out_q(out_anchor)
  );
  // S3 -> S4: special_s4.
  dp_lib_DFFE #(
    .WIDTH(`DP_SPECIAL_W)
  ) ff_s3_s4_special_s4 (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (special_s3_q),
    .out_q(special_s4_q)
  );
  // S3 -> S4: out_all_negative.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s3_s4_out_all_negative (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (all_negative_s3_q),
    .out_q(out_all_negative)
  );
endmodule
