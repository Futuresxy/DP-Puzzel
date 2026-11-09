`include "dp_defs.vh"
// T1H2Q4E8. Owns S1 unpack, S2 products, S3 shared magnitude alignment,
// S4 lane tree and optional HiF4 local e2 fusion. Common group MAX is an S2 side interface;
// BASELINE_V18 excludes E from MAX and routes E signed pairs around the wide shifter.
// Synchronous low reset clears valid only; invalid data registers hold.
// P=LOCAL_W-2 (default 26). I excludes S; SM carries S separately.
// S3 legacy shift magnitude -> TC tree leaf; v1.8 E signed bypass rows follow.
// Precision                    | Shift S | Leaf S | I  | F
// ---------------------------- | ------- | ------ | -- | ----
// TF32 / FP16 / BF16 / MXFP8/6 | 0       | 1      | 2  | P
// MXFP4 / NVFP4                | 0       | 1      | 7  | P-5
// HiF4                         | 0       | 1      | 5  | P-3
// INT8                         | 0       | 1      | 15 | P-13
// v1.8 MX/NV pair (no shift)   | N/A     | 1      | 9  | P-7
// v1.8 HiF4 pair (no shift)    | N/A     | 1      | 7  | P-5
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
// HiF4 legacy        | 1 | 7  | P-3
// HiF4 v1.8          | 1 | 9  | P-5
// INT8               | 1 | 17 | P-13
// TF32/FP16/BF16 append 2/1/1 low zeros after the tree.
// 阅读顺序 / 功能边界：
// S1 u_lane_unpack 保存紧凑尾数/指数/符号；内部在 S2 配对归约特殊分类。
// S2 u_mantissa_mul_bank 产生幅值乘积，u_exponent_add/MAX 同时准备对齐坐标。
// S3 u_local_alignment 完成 pair/落位/RTZ/符号恢复；S4 u_lane_sop_tree 规约。
// r1/r2/r3/r4 前缀明确寄存级；_d 表示本级组合计算、等待捕获的结果。
// ff_sN_sM_* 紧随本级计算，rN_valid 仅表示该级数据是否有效。
// 层内没有独立 ready；两 lane 的公共 MAX 在同拍组合完成，随乘积一起进入 S2。
// verilog_format: off
module dp_lane #(
  // S3 局部幅值对齐窗口宽度；默认 28 位，T/H/Q 的小数位数为 LOCAL_W-2。
  parameter integer LOCAL_W    = `DP_DEFAULT_LOCAL_W,
  // dp_top v1.8: E 固定坐标旁路；默认保留其他顶层的旧接口数值语义。
  parameter integer BASELINE_V18 = 0,
  // S3 补码叶子宽度：在 LOCAL_W 位无符号幅值之外增加一个符号位。
  parameter integer LEAF_W     = LOCAL_W + 1,
  // S4 lane 和的补码宽度：四项树在 LEAF_W 基础上增加 clog2(Q_LANES) 位。
  parameter integer LANE_SOP_W = LEAF_W + $clog2(`DP_Q_LANES)
) (
  // 流水时钟，上升沿捕获。
  input wire                          clock,
  // 同步低有效复位；清除有效控制，payload 由有效位屏蔽。
  input wire                          rst_n,
  // 当前输入请求有效；本 lane 固定推进，无独立反压。
  input wire                          in_valid,
  // 本笔请求的数值格式编码，随数据保存到 r1_datatype。
  input wire [`DP_TYPE_W-1:0]         in_datatype,
  // A 操作数原始 32 位 lane 容器；按 datatype 解释元素布局。
  input wire [`DP_LANE_W-1:0]         in_a,
  // B 操作数原始 32 位 lane 容器，与 A 逐元素配对。
  input wire [`DP_LANE_W-1:0]         in_b,
  // HiF4 A 的两个 e1 元数据位，每位作用于四个元素。
  input wire [1:0]                    in_e1_a,
  // HiF4 B 的两个 e1 元数据位，每位作用于四个元素。
  input wire [1:0]                    in_e1_b,
  // HiF4 A 的 lane 级 e2 元数据位，作用于八个元素。
  input wire                          in_e2_a,
  // HiF4 B 的 lane 级 e2 元数据位，作用于八个元素。
  input wire                          in_e2_b,
  // S2 组合输出：本 lane 有限非零乘积的最大指数和，送 group 求公共 MAX。
  output wire [`DP_PRODUCT_EXP_W-1:0] out_candidate,
  // 本 lane 是否存在可参与 group 指数 MAX 的有限非零乘积。
  output wire                         out_candidate_active,
  // group 在 S2 返回的公共指数参考，与本 lane 乘积同时捕获到 r2。
  input wire [`DP_PRODUCT_EXP_W-1:0]  in_group_max,
  // r4 输出有效；只有有效时才解释对应数值与旁带。
  output wire                         out_valid,
  // S4 输出的有符号 lane 累加和，定点格式见上方 S/I/F 表。
  output wire signed [LANE_SOP_W-1:0] out_sop,
  // S4 输出对应的 group 公共指数参考，尚未在 group 中扣除 bias。
  output wire [`DP_PRODUCT_EXP_W-1:0] out_anchor,
  // S4 特殊分类摘要：NaN、invalid、正 Inf、负 Inf 四位标志。
  output wire [`DP_SPECIAL_W-1:0]     out_special,
  // S4 所有参与项乘积符号均为负的摘要，供 group 保留零结果的负号。
  output wire                         out_all_negative
);
// verilog_format: on
  // generate 元素索引；每个实例处理一个固定元素槽。
  genvar element_index;

  `include "dp_functions.vh"
  // verilog_format: off
  // S1 解包数据有效标志。
  wire                                     r1_valid;
  // S2 乘积及指数旁带有效标志。
  wire                                     r2_valid;
  // S3 对齐叶子有效标志。
  wire                                     r3_valid;
  // S4 lane 和有效标志。
  wire                                     r4_valid;
  // S1 保存的格式，驱动解包视图及 S2 乘法/指数 bank。
  wire [`DP_TYPE_W-1:0]                    r1_datatype;
  // S2 保存的格式，驱动 S3 局部对齐选择。
  wire [`DP_TYPE_W-1:0]                    r2_datatype;
  // S3 保存的格式，驱动 S4 输出低位补零选择。
  wire [`DP_TYPE_W-1:0]                    r3_datatype;

  // ---- S1 紧凑解包与 S2 数值 bank 的互联 ----
  // A/B 尾数各为两个 M16 atom，直接送乘法 bank 按精度选择位片。
  wire [`DP_UNPACK_MANT_W-1:0]             unpack_mantissa_mul_a_mantissas;
  // B 尾数的槽位与 A 一一对应，符号独立于无符号幅值。
  wire [`DP_UNPACK_MANT_W-1:0]             unpack_mantissa_mul_b_mantissas;
  // A 指数为两个 E10 atom，H 取低 8 位、Q 取两个 5 位、HiF4 取 e2。
  wire [`DP_UNPACK_EXP_W-1:0]              unpack_exponent_add_a_exponents;
  // B 紧凑指数，与 A 使用同一格式和位片映射。
  wire [`DP_UNPACK_EXP_W-1:0]              unpack_exponent_add_b_exponents;
  // A 原始紧凑符号出口；乘积符号已由 unpack 配对，本层保留该接口供观察。
  wire [`DP_UNPACK_SIGN_W-1:0]             unpack_lane_a_signs;
  // B 原始紧凑符号出口；不参与本层的幅值乘法。
  wire [`DP_UNPACK_SIGN_W-1:0]             unpack_lane_b_signs;

  // ---- S2 尾数乘法 bank 输出与寄存值 ----
  // 尾数乘法 bank 的组合输出：各元素无符号乘积，等待 S2 捕获。
  wire [`DP_E_LANES*`DP_PRODUCT_W-1:0]     product_magnitudes_d;
  // S2 保存的无符号乘积总线，送局部对齐模块；符号独立传递。
  wire [`DP_E_LANES*`DP_PRODUCT_W-1:0]     r2_product_magnitudes;

  // ---- S2 指数 bank 输入与输出 ----
  // 指数 bank 的组合输出：各元素 A/B 指数之和，等待 S2 捕获。
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] product_exponents_d;
  // S2 保存的逐元素指数和，用于 S3 计算对齐差值。
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] r2_product_exponents;

  // ---- S2 符号、活动掩码及特殊分类 ----
  // 逐元素 A/B 符号异或，得到乘积符号；包含零乘积。
  wire [`DP_E_LANES-1:0]                   product_negative_d;
  // 逐元素有限非零且属于当前模式的标志，仅用于数值指数 MAX。
  wire [`DP_E_LANES-1:0]                   product_active_d;
  // S2 保存的乘积符号，与 r2_product_magnitudes 对应同一请求。
  wire [`DP_E_LANES-1:0]                   r2_product_negative;
  // S2 保存的有限非零活动掩码，供 S3 对齐使用。
  wire [`DP_E_LANES-1:0]                   r2_product_active;
  // unpack 内配对/归约后的分类摘要，包含 0*Inf、sNaN 和正负 Inf 冲突。
  wire [`DP_SPECIAL_W-1:0]                 lane_special_flags_d;
  // S2 保存的 lane 特殊分类摘要。
  wire [`DP_SPECIAL_W-1:0]                 r2_special_flags;
  // S3 延迟保存的特殊分类，与对齐叶子同拍。
  wire [`DP_SPECIAL_W-1:0]                 r3_special_flags;
  // S4 延迟保存的特殊分类，与输出和同拍。
  wire [`DP_SPECIAL_W-1:0]                 r4_special_flags;
  // 所有参与项的乘积符号均为负；零乘积参与，未用槽视为归约与的 1。
  wire                                     all_products_negative_d;
  // S2 保存的全负符号摘要，用于最终零符号处理。
  wire                                     r2_all_products_negative;
  // S3 延迟保存的全负符号摘要，与对齐叶子同拍。
  wire                                     r3_all_products_negative;
  // S2 保存的两 lane 公共指数参考，和乘积同步捕获。
  wire [`DP_PRODUCT_EXP_W-1:0]             r2_group_anchor;
  // S3 延迟保存的公共指数参考，与对齐叶子同拍。
  wire [`DP_PRODUCT_EXP_W-1:0]             r3_group_anchor;

  // ---- S3 对齐模块与 S4 累加树的互联 ----
  // 局部对齐模块的四路补码叶子输出，等待 S3 捕获。
  wire [`DP_Q_LANES*LEAF_W-1:0]            aligned_leaves_d;
  // S3 保存的四路补码叶子，作为 S4 平衡加法树输入。
  wire [`DP_Q_LANES*LEAF_W-1:0]            r3_aligned_leaves;
  // S4 累加树的组合输出；已保留树增长位，尚未按 T/H 模式补低零。
  wire signed [LANE_SOP_W-1:0]             lane_sum_d;
  // verilog_format: on
  // verilog_format: off
  assign out_valid   = r4_valid;
  assign out_special = r4_special_flags;
  // verilog_format: on
  // [S1 解包 / S2 分类] A/B 共用一个入口，各自保存 M32/E20/S8 及分类。
  // unpack 只做一次编码译码；bank 只选择紧凑字段，不重新解码 hidden bit/特殊值。
  // 分类在 unpack 内按 A/B 对应元素配对再归约，仍由本模块 S2 DFF 捕获。
  // 原始 A/B 符号输出在本层无需使用，乘积符号及 all_negative 已由 unpack 生成。
  dp_lane_unpack #(.PRECISION_GATING(1)) u_lane_unpack (
    .clock                 (clock),
    .rst_n                 (rst_n),
    .in_valid              (in_valid),
    .in_datatype           (in_datatype),
    .in_registered_datatype(r1_datatype),
    .in_a                  (in_a),
    .in_b                  (in_b),
    .in_e1_a               (in_e1_a),
    .in_e1_b               (in_e1_b),
    .in_e2_a               (in_e2_a),
    .in_e2_b               (in_e2_b),
    .out_a_mantissas       (unpack_mantissa_mul_a_mantissas),
    .out_b_mantissas       (unpack_mantissa_mul_b_mantissas),
    .out_a_exponents       (unpack_exponent_add_a_exponents),
    .out_b_exponents       (unpack_exponent_add_b_exponents),
    .out_a_signs           (unpack_lane_a_signs),
    .out_b_signs           (unpack_lane_b_signs),
    .out_product_negative  (product_negative_d),
    .out_product_active    (product_active_d),
    .out_special           (lane_special_flags_d),
    .out_all_negative      (all_products_negative_d)
  );

  // [S1 寄存边界] 保存 valid/类型，与解包模块内的 S1 幅值、指数和符号同拍。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(in_valid), .out_q(r1_valid));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s0_s1_type_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(in_datatype), .out_q(r1_datatype));
  // verilog_format: on

  // [S2 指数计算] 只按 r1_datatype 选择 E10 中的字段，共享宽/窄加法器。
  dp_exponent_bank u_exponent_add (
    .in_datatype   (r1_datatype),
    .in_enable     (r1_valid),
    .in_a_exponents(unpack_exponent_add_a_exponents),
    .in_b_exponents(unpack_exponent_add_b_exponents),
    .out_exponents (product_exponents_d)
  );

  // Exponent MAX does not depend on multiplier outputs or returned group MAX.
  // 指数 MAX 输入总线：每个无符号指数和前补 0，供有符号比较器使用。
  wire        [`DP_E_LANES*(`DP_PRODUCT_EXP_W+1)-1:0] product_exponent_candidates;
  // 本 lane MAX 的组合结果，多一位保证正指数值不被解释为负。
  wire signed [                  `DP_PRODUCT_EXP_W:0] lane_max_exponent;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_candidate
      // verilog_format: off
      assign product_exponent_candidates[element_index*(`DP_PRODUCT_EXP_W+1)+:`DP_PRODUCT_EXP_W+1] = { 1'b0, product_exponents_d[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] };
      // verilog_format: on
    end
  endgenerate

  // E 不参与指数比较；HiF4 e2 和仍独立保存在窄旁带中。
  wire [`DP_E_LANES-1:0] exponent_max_active;
  assign exponent_max_active = ((BASELINE_V18 != 0) & r1_is_e) ? 0 : product_active_d;
  dp_max_tree #(
    .N(`DP_E_LANES),
    .W(`DP_PRODUCT_EXP_W + 1)
  ) u_lane_exponent_max (
    .in_values (product_exponent_candidates),
    .in_active (exponent_max_active),
    .out_max   (lane_max_exponent),
    .out_active(out_candidate_active)
  );

  // verilog_format: off
  assign out_candidate = lane_max_exponent[`DP_PRODUCT_EXP_W-1:0];
  // verilog_format: on

  // [S2 尾数乘法] bank 只计算无符号幅值；乘积符号、指数、分类另行同拍寄存。
  dp_mantissa_bank u_mantissa_mul_bank (
    .in_datatype   (r1_datatype),
    .in_enable     (r1_valid),
    .in_a_mantissas(unpack_mantissa_mul_a_mantissas),
    .in_b_mantissas(unpack_mantissa_mul_b_mantissas),
    .out_products  (product_magnitudes_d)
  );

  // [精度门控] 每级捕获使用源级类型，消费使用目标级类型；允许逐拍混精度。
  // E coefficient 4x4 幅值乘积只需 8 位；其余位是共享容器扩展位。
  localparam integer E_PRODUCT_W = 2 * `DP_MUL_LO;
  // 四项 E pair 含 HiF4 两位对齐余量；默认 29 位叶子低 17 位恒零。
  localparam integer E_LEAF_W = `DP_E_PAIR_W + `DP_E_GUARD;
  localparam integer E_LEAF_PAD = LEAF_W - E_LEAF_W;
  // 与各级有效载荷同拍的 E/HiF4 选择，不使用当前 top 输入控制在途数据。
  wire r1_is_e;
  wire r2_is_e;
  wire r3_is_e;
  wire r1_is_hif4;
  wire r2_is_hif4;
  assign r1_is_e    = (r1_datatype == `DP_DT_MXFP4) | (r1_datatype == `DP_DT_NVFP4) | (r1_datatype == `DP_DT_HIF4);
  assign r2_is_e    = (r2_datatype == `DP_DT_MXFP4) | (r2_datatype == `DP_DT_NVFP4) | (r2_datatype == `DP_DT_HIF4);
  assign r3_is_e    = (r3_datatype == `DP_DT_MXFP4) | (r3_datatype == `DP_DT_NVFP4) | (r3_datatype == `DP_DT_HIF4);
  assign r1_is_hif4 = r1_datatype == `DP_DT_HIF4;
  assign r2_is_hif4 = r2_datatype == `DP_DT_HIF4;

  // [S2 寄存边界] 捕获乘积、指数/公共 anchor、符号和特殊分类，供 S3 对齐使用。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  // 按槽拆分乘积的低位和高位；未用槽及关闭的高位在读取时补零，不能泄漏旧值。
  genvar product_index;
  generate
    for (product_index = 0; product_index < `DP_E_LANES; product_index = product_index + 1) begin : g_product_register
      wire product_slot_en;
      wire product_upper_en;
      wire [E_PRODUCT_W-1:0] r2_product_low;
      wire [`DP_PRODUCT_W-E_PRODUCT_W-1:0] r2_product_upper;
      assign product_slot_en  = rst_n & r1_valid & (product_index < elements(r1_datatype));
      assign product_upper_en = product_slot_en & ~r1_is_e;
      dp_lib_DFFE #(.WIDTH(E_PRODUCT_W))
      ff_s1_s2_product_low (.clock(clock), .in_en(product_slot_en), .in_d(product_magnitudes_d[product_index*`DP_PRODUCT_W+:E_PRODUCT_W]), .out_q(r2_product_low));
      dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_W-E_PRODUCT_W))
      ff_s1_s2_product_upper (.clock(clock), .in_en(product_upper_en), .in_d(product_magnitudes_d[product_index*`DP_PRODUCT_W+E_PRODUCT_W+:`DP_PRODUCT_W-E_PRODUCT_W]), .out_q(r2_product_upper));
      assign r2_product_magnitudes[product_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (product_index >= elements(r2_datatype)) ? {`DP_PRODUCT_W{1'b0}} :
        { (r2_is_e ? {(`DP_PRODUCT_W-E_PRODUCT_W){1'b0}} : r2_product_upper), r2_product_low };
    end
  endgenerate
  // 非 E 指数保持原布局；HiF4 只保存一次两位 e2 和，其余 E 在消费端恢复零。
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] r2_non_e_exponents;
  wire [`DP_E_GUARD-1:0] r2_hif4_exponent;
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES * `DP_PRODUCT_EXP_W))
  ff_s1_s2_exponents (.clock(clock), .in_en(rst_n & r1_valid & ~r1_is_e), .in_d(product_exponents_d), .out_q(r2_non_e_exponents));
  dp_lib_DFFE #(.WIDTH(`DP_E_GUARD))
  ff_s1_s2_hif4_exponent (.clock(clock), .in_en(rst_n & r1_valid & r1_is_hif4), .in_d(product_exponents_d[0+:`DP_E_GUARD]), .out_q(r2_hif4_exponent));
  assign r2_product_exponents = r2_is_e ? {`DP_E_LANES{ {(`DP_PRODUCT_EXP_W-`DP_E_GUARD){1'b0}}, (r2_is_hif4 ? r2_hif4_exponent : {`DP_E_GUARD{1'b0}}) }} : r2_non_e_exponents;
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s1_s2_negative (.clock(clock), .in_en(rst_n & r1_valid), .in_d(product_negative_d), .out_q(r2_product_negative));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s1_s2_active (.clock(clock), .in_en(rst_n & r1_valid), .in_d(product_active_d), .out_q(r2_product_active));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s1_s2_anchor_s2 (.clock(clock), .in_en(rst_n & r1_valid), .in_d(in_group_max), .out_q(r2_group_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s1_s2_type_s2 (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_datatype), .out_q(r2_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s1_s2_special_s2 (.clock(clock), .in_en(rst_n & r1_valid), .in_d(lane_special_flags_d), .out_q(r2_special_flags));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_all_negative_s2 (.clock(clock), .in_en(rst_n & r1_valid), .in_d(all_products_negative_d), .out_q(r2_all_products_negative));
  // verilog_format: on

  // [S3 局部对齐] 整个选择/pair/幅值移位/符号恢复由一个组合模块负责。
  // 输入是 S2 寄存器；输出在 ff_s2_s3_leaves 捕获，随后进入 S4 累加树。
  dp_lane_align #(
    .LOCAL_W(LOCAL_W),
    .LEAF_W (LEAF_W),
    .E_FIXED_COORD(BASELINE_V18)
  ) u_local_alignment (
    .in_valid    (r2_valid),
    .in_datatype (r2_datatype),
    .in_products (r2_product_magnitudes),
    .in_negative (r2_product_negative),
    .in_active   (r2_product_active),
    .in_anchor   (r2_group_anchor),
    .in_exponents(r2_product_exponents),
    .out_leaves  (aligned_leaves_d)
  );

  // HiF4 的局部 e2_a+e2_b 只用于 S4 树后小移位，不经过跨 lane MAX。
  wire [`DP_E_GUARD-1:0] r3_hif4_exponent;
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(`DP_E_GUARD))
  ff_s2_s3_hif4_exponent (.clock(clock), .in_en(rst_n & r2_valid & r2_is_hif4 & (BASELINE_V18 != 0)), .in_d(r2_hif4_exponent), .out_q(r3_hif4_exponent));
  // verilog_format: on

  // [S3 寄存边界] 捕获对齐叶子及同请求旁带，下一段只使用本级寄存值。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  // E pair 的低 E_LEAF_PAD 位为结构零，按精度关闭这些位的寄存器。
  // HiF4 delta<=2，故低 LEAF_W-(PAIR_W+GUARD) 位恒零；高位包含补码符号。
  genvar leaf_index;
  generate
    for (leaf_index = 0; leaf_index < `DP_Q_LANES; leaf_index = leaf_index + 1) begin : g_leaf_register
      wire [E_LEAF_W-1:0] r3_leaf_upper;
      wire [E_LEAF_PAD-1:0] r3_leaf_lower;
      dp_lib_DFFE #(.WIDTH(E_LEAF_W))
      ff_s2_s3_leaf_upper (.clock(clock), .in_en(rst_n & r2_valid), .in_d(aligned_leaves_d[leaf_index*LEAF_W+E_LEAF_PAD+:E_LEAF_W]), .out_q(r3_leaf_upper));
      dp_lib_DFFE #(.WIDTH(E_LEAF_PAD))
      ff_s2_s3_leaf_lower (.clock(clock), .in_en(rst_n & r2_valid & ~r2_is_e), .in_d(aligned_leaves_d[leaf_index*LEAF_W+:E_LEAF_PAD]), .out_q(r3_leaf_lower));
      assign r3_aligned_leaves[leaf_index*LEAF_W+:LEAF_W] = {r3_leaf_upper, (r3_is_e ? {E_LEAF_PAD{1'b0}} : r3_leaf_lower)};
    end
  endgenerate
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s2_s3_anchor_s3 (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_group_anchor), .out_q(r3_group_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s2_s3_type_s3 (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_datatype), .out_q(r3_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s2_s3_special_s3 (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_special_flags), .out_q(r3_special_flags));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_all_negative_s3 (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_all_products_negative), .out_q(r3_all_products_negative));
  // verilog_format: on

  // [S4 lane 累加树] 四个 S3 补码叶子平衡相加，每层增长一位，F 不变。
  // T/H 的低位静态补零在 S4 输出 DFF 输入完成，以统一 lane 容器坐标。
  dp_sum_tree #(
    .N(`DP_Q_LANES),
    .W(LEAF_W)
  ) u_lane_sop_tree (
    .in_values(r3_aligned_leaves),
    .out_sum  (lane_sum_d)
  );

  // [S4 输出选择] 组合数值选择在 DFF 外明确表达，寄存器只保存选定结果。
  // S4 格式选择后的 lane 和：TF32 低补 2 零，FP16/BF16 低补 1 零，其余直通。
  wire [LANE_SOP_W-1:0] lane_sop_d;
  // verilog_format: off
  // E 已是带符号 pair；树结果保留 14 位容器，先扩位再融合 e2。
  // MX/NV: S1I9F2 <<2；HiF4: S1I7F4 <<p；统一 S1I9F4 后低补 LANE_SOP_W-14 零。
  wire [`DP_E_GUARD-1:0] e_lane_shift;
  assign e_lane_shift = (r3_datatype == `DP_DT_HIF4) ? r3_hif4_exponent : `DP_E_GUARD;
  assign lane_sop_d = (r3_datatype == `DP_DT_TF32)                                 ? lane_sum_d << $clog2(`DP_Q_LANES) :
                     ((r3_datatype == `DP_DT_FP16) | (r3_datatype == `DP_DT_BF16)) ? lane_sum_d << ($clog2(`DP_Q_LANES) - 1) :
                     ((BASELINE_V18 != 0) & r3_is_e)                           ? lane_sum_d << e_lane_shift :
                     lane_sum_d;
  // verilog_format: on

  // [S4 寄存边界] 捕获 lane 和及输出旁带；只在 out_valid 有效时解释输出。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(r4_valid));
  dp_lib_DFFE #(.WIDTH(LANE_SOP_W))
  ff_s3_s4_out_sop (.clock(clock), .in_en(rst_n & r3_valid), .in_d(lane_sop_d), .out_q(out_sop));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s3_s4_out_anchor (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_group_anchor), .out_q(out_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s3_s4_special_s4 (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_special_flags), .out_q(r4_special_flags));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s3_s4_out_all_negative (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_all_products_negative), .out_q(out_all_negative));
  // verilog_format: on

endmodule
