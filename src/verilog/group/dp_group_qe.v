`include "dp_defs.vh"
// Q8E16: two synchronized lanes, S2 common MAX, S5 abs/scale/LZD.
// Owns S1 scale decode and S2 scale-pair arithmetic; transport stops at S4.
// Output is unnormalized sign/magnitude, A_raw=alpha-F+(M-1), plus z.
// S5 group tree adds one integer bit to each S4 TC SOP, holding F.
// S2 unsigned scale pair.
// Precision / signal | S | I | F
// ------------------ | - | - | -
// A/B scale          | 0 | 1 | 3
// Scale pair         | 0 | 2 | 6
// Only NVFP4/HiF4 use the compact magnitude multiply.
// P=LOCAL_W-2 (default 26). SM has one separate sign bit.
// S5 group output (SM).
// Precision / signal | S | I  | F
// ------------------ | - | -- | ----
// MXFP8 / MXFP6      | 1 | 5  | P
// MXFP4              | 1 | 10 | P-5
// NVFP4              | 1 | 12 | P-7
// HiF4 v1.9          | 1 | 12 | P-7
// HiF4 legacy        | 1 | 10 | P-5
// LZD reads the listed I/F as unsigned magnitude (S=0).
// 阅读顺序 / 功能边界：
// 数据主路：两个 QE lane -> S5 两项树/abs -> scale 或旁路/LZD -> token。
// 旁带：S1 scale 解包，S2 系数积/指数和，再延迟到 S5；S2 公共 MAX 回送两 lane。
// 两个 lane 共享 valid 和时钟，没有独立握手；MAX 只产生共同坐标，不等待 lane 结果。
module dp_group_qe #(
  // v1.9 固定坐标 E 路径、S3 A_raw 和 S5 compare_exp；0 保留旧回放。
  parameter integer ARCHITECTURE_V19 = 0,
  // 仅影响 QE lane 的 S1 内部表示，组 S5 token 与数值坐标不变。
  parameter integer COMPACT_UNPACK = 0,
  // S3 局部幅值对齐窗口，改变时下游 lane/group 位宽同步推导。
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  // S4 lane 和位宽：有符号叶子经四项树增加两位整数位。
  parameter integer LANE_SOP_W = LOCAL_W + 1 + $clog2(`DP_Q_LANES),
  // S5 两 lane 合并的补码总宽，较 lane 再增加一位。
  parameter integer GROUP_W = LANE_SOP_W + $clog2(`DP_LANES),
  // 符号分离后的幅值位宽，不含符号。
  parameter integer MAG_W = GROUP_W - 1,
  // 有符号指数坐标宽度，由合法幅值窗口推导。
  parameter integer ANCHOR_W = anchor_width(MAG_W)
) (
  // 上升沿流水时钟。
  input wire clock,
  // 同步低有效复位，只复位控制；数据由 valid 屏蔽。
  input wire rst_n,
  // 原子请求有效，输入每拍最多接收一笔。
  input wire in_valid,
  // 本笔 Q/E 元素类型；由父层排除不支持的 T/H/INT8。
  input wire [`DP_TYPE_W-1:0] in_datatype,
  // A 原始打包操作数，按 group/lane 低位优先切片。
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_a,
  // B 原始打包操作数，与 A 同容量且逐元素配对。
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_b,
  // A 的每组 scale 字节，由测试/上游按格式广播到各组。
  input wire [`DP_SCALE_W-1:0] in_scale_a,
  // B 的每组 scale 字节，布局与 A 一致。
  input wire [`DP_SCALE_W-1:0] in_scale_b,
  // 两侧共用的已验证 scale 编码类型。
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_datatype,
  // HiF4 e1 元数据，每位对应四个元素。
  input wire [3:0] in_e1_a,
  // HiF4 e1 元数据，每位对应四个元素。
  input wire [3:0] in_e1_b,
  // HiF4 e2 元数据，每位对应一个八元素 lane。
  input wire [1:0] in_e2_a,
  // HiF4 e2 元数据，每位对应一个八元素 lane。
  input wire [1:0] in_e2_b,
  // 输出有效，延迟固定且不支持反压。
  output wire out_valid,
  // S5 token 的独立符号位，包含负零语义。
  output wire out_negative,
  // S5 token 幅值，保留原始坐标，不在此先移位规格化。
  output wire [MAG_W-1:0] out_magnitude,
  // S5 token 原始指数坐标 A_raw，真实最高位指数为 A_raw-z。
  output wire signed [ANCHOR_W-1:0] out_anchor,
  // 幅值前导零数，供 S6 合并规格化与对齐。
  output wire signed [ANCHOR_W-1:0] out_compare_exp,
  output wire [$clog2(MAG_W+1)-1:0] out_z,
  // NaN/invalid/正 Inf/负 Inf 的独立分类摘要。
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar lane_index;

  `include "dp_functions.vh"
  // 两路无符号 scale 尾数相乘的完整系数位宽。
  localparam integer COEFF_W = 2 * `DP_SCALE_M;
  // scale 乘法前去除结构零后的有效幅值宽度。
  localparam integer SCALE_MAG_W = `DP_SCALE_SOP_W - 1;
  // 组和低位固定补零数量，压缩时仅移除这些结构零。
  localparam integer STRUCTURAL_DROP = GROUP_W - `DP_SCALE_SOP_W;
  // 14x8 无符号 scale 乘积的自然宽度。
  localparam integer SCALE_PRODUCT_W = SCALE_MAG_W + COEFF_W;
  // 乘积补齐公共 group 幅值容器所需的低位零数。
  localparam integer SCALE_LOW_PAD = MAG_W - SCALE_PRODUCT_W;
  // S1 保存本请求的 valid。
  wire r1_valid;
  // S2 保存本请求的 valid。
  wire r2_valid;
  // S3 保存本请求的 valid。
  wire r3_valid;
  // S4 保存本请求的 valid。
  wire r4_valid;
  // S1 保存本请求的 datatype。
  wire [`DP_TYPE_W-1:0] r1_datatype;
  // S2 保存本请求的 datatype。
  wire [`DP_TYPE_W-1:0] r2_datatype;
  // S3 保存本请求的 datatype。
  wire [`DP_TYPE_W-1:0] r3_datatype;
  // S4 保存本请求的 datatype。
  wire [`DP_TYPE_W-1:0] r4_datatype;
  wire [`DP_LANES*LANE_SOP_W-1:0] lane_group_sum;
  wire [`DP_LANES*((`DP_Q_EXP_W+1)+1)-1:0] lane_exponent_max_candidates;
  wire [`DP_LANES-1:0] lane_exponent_max_active;
  wire [`DP_LANES-1:0] lane_group_all_negative;
  wire [`DP_LANES-1:0] lane_group_valid;
  wire [`DP_LANES*`DP_SPECIAL_W-1:0] lane_group_special;
  wire [(`DP_Q_EXP_W+1)-1:0] lane_group_anchor[0:`DP_LANES-1];
  wire signed [(`DP_Q_EXP_W+1):0] exponent_max_lane_anchor;
  wire max_active;
  // [lane 分发] 每 lane 接收连续 32 位 A/B 切片和对应 HiF4 e1/e2。
  // 同一 group 的 scale 在父层只解包一份 A 和一份 B，由两个 lane 的合并结果共用。
  generate
    for (lane_index = 0; lane_index < `DP_LANES; lane_index = lane_index + 1) begin : g_lane
      wire [(`DP_Q_EXP_W+1)-1:0] candidate;
      wire [  `DP_SPECIAL_W-1:0] special_value;
      dp_lane_qe #(
          .ARCHITECTURE_V19(ARCHITECTURE_V19),
          .COMPACT_UNPACK(COMPACT_UNPACK),
          .LOCAL_W(LOCAL_W)
      ) u_lane (
          .clock               (clock),
          .rst_n               (rst_n),
          .in_valid            (in_valid),
          .in_datatype         (in_datatype),
          .in_a                (in_a[lane_index*`DP_LANE_W+:`DP_LANE_W]),
          .in_b                (in_b[lane_index*`DP_LANE_W+:`DP_LANE_W]),
          .in_e1_a             (in_e1_a[lane_index*2+:2]),
          .in_e1_b             (in_e1_b[lane_index*2+:2]),
          .in_e2_a             (in_e2_a[lane_index]),
          .in_e2_b             (in_e2_b[lane_index]),
          .out_candidate       (candidate),
          .out_candidate_active(lane_exponent_max_active[lane_index]),
          .in_group_max        (exponent_max_lane_anchor[(`DP_Q_EXP_W+1)-1:0]),
          .out_valid           (lane_group_valid[lane_index]),
          .out_sop             (lane_group_sum[lane_index*LANE_SOP_W+:LANE_SOP_W]),
          .out_anchor          (lane_group_anchor[lane_index]),
          .out_special         (special_value),
          .out_all_negative    (lane_group_all_negative[lane_index])
      );
      assign lane_exponent_max_candidates[lane_index*((`DP_Q_EXP_W+1)+1)+:(`DP_Q_EXP_W+1)+1] = {1'b0, candidate};
      assign lane_group_special[lane_index*`DP_SPECIAL_W+:`DP_SPECIAL_W]                     = special_value;
    end
  endgenerate
  // [S2 公共 MAX] 从两 lane 的有限非零候选选同一个原始指数和。
  // 该组合值在各 lane 的 S2 DFF 捕获，与乘积同时到达；并非跨事务反馈环。
  dp_max_tree #(
      .N(`DP_LANES),
      .W((`DP_Q_EXP_W + 1) + 1)
  ) u_group_exponent_max (
      .in_values (lane_exponent_max_candidates),
      .in_active (lane_exponent_max_active),
      .out_max   (exponent_max_lane_anchor),
      .out_active(max_active)
  );
  wire [`DP_SCALE_M-1:0] scale_a_magnitude_d;
  wire [`DP_SCALE_M-1:0] scale_b_magnitude_d;
  wire [`DP_EXP_W-1:0] scale_a_exponent_d;
  wire [`DP_EXP_W-1:0] scale_b_exponent_d;
  wire scale_a_nan_d;
  wire scale_b_nan_d;
  wire [`DP_SCALE_M-1:0] r1_scale_a_magnitude;
  wire [`DP_SCALE_M-1:0] r1_scale_b_magnitude;
  wire [`DP_EXP_W-1:0] r1_scale_a_exponent;
  wire [`DP_EXP_W-1:0] r1_scale_b_exponent;
  wire r1_scale_nan;
  wire [COEFF_W-1:0] scale_coefficient_d;
  // S2 保存本请求的 scale_coefficient。
  wire [COEFF_W-1:0] r2_scale_coefficient;
  // S3 保存本请求的 scale_coefficient。
  wire [COEFF_W-1:0] r3_scale_coefficient;
  // S4 保存本请求的 scale_coefficient。
  wire [COEFF_W-1:0] r4_scale_coefficient;
  // S2 保存本请求的 scale_exponent。
  wire [`DP_PRODUCT_EXP_W-1:0] r2_scale_exponent;
  // S3 保存本请求的 scale_exponent。
  wire [`DP_PRODUCT_EXP_W-1:0] r3_scale_exponent;
  // S4 保存本请求的 scale_exponent。
  wire [`DP_PRODUCT_EXP_W-1:0] r4_scale_exponent;
  // S2 保存本请求的 scale_nan。
  wire r2_scale_nan;
  // S3 保存本请求的 scale_nan。
  wire r3_scale_nan;
  // S4 保存本请求的 scale_nan。
  wire r4_scale_nan;
  // [scale 旁路准备：S1 -> S2] I1F3尾数；v1.9 signed8无偏指数，legacy公共bias。
  // S2 尾数相乘形成 I2F6 系数，同时指数相加；NaN 分类独立传递，不靠零幅值推断。
  dp_scale_unpack #(.UNBIASED_EXPONENT(ARCHITECTURE_V19)) u_scale_unpack_a (
      .in_data      (in_scale_a),
      .in_datatype  (in_scale_datatype),
      .out_magnitude(scale_a_magnitude_d),
      .out_exponent (scale_a_exponent_d),
      .out_nan      (scale_a_nan_d)
  );
  dp_scale_unpack #(.UNBIASED_EXPONENT(ARCHITECTURE_V19)) u_scale_unpack_b (
      .in_data      (in_scale_b),
      .in_datatype  (in_scale_datatype),
      .out_magnitude(scale_b_magnitude_d),
      .out_exponent (scale_b_exponent_d),
      .out_nan      (scale_b_nan_d)
  );

  // [S1 寄存边界] 保存 scale 解包值、类型和 valid，供下一段系数预乘使用。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(in_valid), .out_q(r1_valid));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s0_s1_datatype (.clock(clock), .in_en(rst_n & in_valid), .in_d(in_datatype), .out_q(r1_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_SCALE_M))
  ff_s0_s1_scale_a_magnitude (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_magnitude_d), .out_q(r1_scale_a_magnitude));
  dp_lib_DFFE #(.WIDTH(`DP_SCALE_M))
  ff_s0_s1_scale_b_magnitude (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_b_magnitude_d), .out_q(r1_scale_b_magnitude));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_scale_a_exponent (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_exponent_d), .out_q(r1_scale_a_exponent));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_scale_b_exponent (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_b_exponent_d), .out_q(r1_scale_b_exponent));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s0_s1_scale_nan (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_nan_d | scale_b_nan_d), .out_q(r1_scale_nan));
  // verilog_format: on

  dp_mul_unsigned #(
      .A_W(`DP_SCALE_M),
      .B_W(`DP_SCALE_M)
  ) u_scale_pair_mul (
      .in_a       (r1_scale_a_magnitude),
      .in_b       (r1_scale_b_magnitude),
      .out_product(scale_coefficient_d)
  );

  // scale 无偏指数：signed8 + signed8 -> signed9，符号扩展不可用零扩展替代。
  wire [`DP_PRODUCT_EXP_W-1:0] scale_exponent_sum_d;
  wire [`DP_Q_EXP_W:0] r2_group_max;
  assign scale_exponent_sum_d = (ARCHITECTURE_V19 != 0) ?
      {r1_scale_a_exponent[`DP_EXP_W-1], r1_scale_a_exponent} +
      {r1_scale_b_exponent[`DP_EXP_W-1], r1_scale_b_exponent} :
      {1'b0, r1_scale_a_exponent} + {1'b0, r1_scale_b_exponent};
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(`DP_Q_EXP_W+1))
  ff_s1_s2_group_max (.clock(clock), .in_en(rst_n & r1_valid & (ARCHITECTURE_V19 != 0)), .in_d(exponent_max_lane_anchor[`DP_Q_EXP_W:0]), .out_q(r2_group_max));
  // verilog_format: on

  // [S2 寄存边界] 保存 scale 系数积/指数和；两 lane 在内部捕获共同 MAX。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s1_s2_datatype (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_datatype), .out_q(r2_datatype));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s1_s2_scale_coefficient (.clock(clock), .in_en(rst_n & r1_valid), .in_d(scale_coefficient_d), .out_q(r2_scale_coefficient));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s1_s2_scale_exponent (.clock(clock), .in_en(rst_n & r1_valid), .in_d(scale_exponent_sum_d), .out_q(r2_scale_exponent));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_scale_nan (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_scale_nan), .out_q(r2_scale_nan));
  // verilog_format: on

  // S3 提前计算 A_raw；Q 的公共偏置为15，E 已将 e2 融入幅值。
  // 常量 M-1-F 吸收所有结构补零，scale 指数已经去偏，不再扣254。
  localparam integer Q_ANCHOR_OFFSET = MAG_W-1-(LOCAL_W-2)-2*`DP_Q_BIAS;
  localparam signed [ANCHOR_W-1:0] MX_ANCHOR_OFFSET = 9;
  localparam signed [ANCHOR_W-1:0] SCALED_E_ANCHOR_OFFSET = 11;
  wire signed [ANCHOR_W-1:0] raw_anchor_d;
  wire signed [ANCHOR_W-1:0] r3_raw_anchor;
  wire signed [ANCHOR_W-1:0] r4_raw_anchor;
  wire signed [ANCHOR_W-1:0] element_anchor_d;
  wire signed [ANCHOR_W-1:0] scale_anchor_d;
  wire signed [ANCHOR_W-1:0] coordinate_offset_d;
  assign element_anchor_d = $signed({{(ANCHOR_W-`DP_Q_EXP_W-1){1'b0}}, r2_group_max});
  assign scale_anchor_d = $signed({{(ANCHOR_W-`DP_PRODUCT_EXP_W){r2_scale_exponent[`DP_PRODUCT_EXP_W-1]}}, r2_scale_exponent});
  assign coordinate_offset_d = (r2_datatype < `DP_DT_MXFP4) ? $signed(Q_ANCHOR_OFFSET[ANCHOR_W-1:0]) :
      (r2_datatype == `DP_DT_MXFP4) ? MX_ANCHOR_OFFSET : SCALED_E_ANCHOR_OFFSET;
  assign raw_anchor_d = element_anchor_d + scale_anchor_d + coordinate_offset_d;
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s2_s3_raw_anchor (.clock(clock), .in_en(rst_n & r2_valid & (ARCHITECTURE_V19 != 0)), .in_d(raw_anchor_d), .out_q(r3_raw_anchor));
  // verilog_format: on

  // [S3 寄存边界] scale 旁带保持数值并延迟一拍，与 lane 的 S3 对齐同行。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s2_s3_datatype (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_datatype), .out_q(r3_datatype));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s2_s3_scale_coefficient (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_scale_coefficient), .out_q(r3_scale_coefficient));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s2_s3_scale_exponent (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_scale_exponent), .out_q(r3_scale_exponent));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_scale_nan (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_scale_nan), .out_q(r3_scale_nan));
  // verilog_format: on

  // S4 仅延迟已算好的 A_raw，与 lane 输出及 scale 系数保持同拍。
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s3_s4_raw_anchor (.clock(clock), .in_en(rst_n & r3_valid & (ARCHITECTURE_V19 != 0)), .in_d(r3_raw_anchor), .out_q(r4_raw_anchor));
  // verilog_format: on

  // [S4 寄存边界] scale 旁带继续延迟，与两个 lane 的 S4 和同拍到达 S5。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(r4_valid));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s3_s4_datatype (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_datatype), .out_q(r4_datatype));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s3_s4_scale_coefficient (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_scale_coefficient), .out_q(r4_scale_coefficient));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s3_s4_scale_exponent (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_scale_exponent), .out_q(r4_scale_exponent));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s3_s4_scale_nan (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_scale_nan), .out_q(r4_scale_nan));
  // verilog_format: on

  // [S5 组规约] 两个 S4 lane 和已有相同 anchor/F；用一层树扩展一位后相加。
  // 先完成两 lane 的抵消再取绝对值，后续 14x8 乘法只处理幅值，符号独立旁传。
  wire signed [GROUP_W-1:0] group_sum;
  dp_sum_tree #(
      .N(`DP_LANES),
      .W(LANE_SOP_W)
  ) u_group_sop_add (
      .in_values(lane_group_sum),
      .out_sum  (group_sum)
  );
  wire inject_scale;
  assign inject_scale = (r4_datatype == `DP_DT_NVFP4 | r4_datatype == `DP_DT_HIF4) & r4_valid;
  // Both branches share the absolute value. NV/HiF compact the magnitude
  // by slicing off structural low zeros; their legal group sums fit SCALE_MAG_W.
  wire group_negative;
  assign group_negative = group_sum[GROUP_W-1];
  wire [GROUP_W-1:0] absolute_sop;
  assign absolute_sop = group_negative ? -group_sum : group_sum;
  wire [SCALE_MAG_W-1:0] compact_magnitude;
  assign compact_magnitude = inject_scale ? absolute_sop[STRUCTURAL_DROP+:SCALE_MAG_W] : 0;
  wire [COEFF_W-1:0] compact_coefficient;
  assign compact_coefficient = inject_scale ? r4_scale_coefficient : 0;
  wire [SCALE_PRODUCT_W-1:0] scale_product;
  // [S5 scale 注入] 仅 NVFP4/HiF4 启用 14x8 无符号乘法，22 位输出完整保留。
  // 旁路和乘法结果都补零放入同宽 S5 magnitude 容器；MX 的 2^scale 由 anchor 表达。
  dp_scale_multiply u_group_scale_mul (
      .in_magnitude  (compact_magnitude),
      .in_coefficient(compact_coefficient),
      .out_product   (scale_product)
  );
  wire [MAG_W-1:0] magnitude_d;
  assign magnitude_d = inject_scale ? {scale_product, {SCALE_LOW_PAD{1'b0}}} : absolute_sop[MAG_W-1:0];
  wire negative_d;
  assign negative_d = group_negative | (group_sum == 0 & (&lane_group_all_negative));
  wire [$clog2(MAG_W+1)-1:0] z_d;
  wire magnitude_active;
  // [S5 LZD] 只检测补零后幅值的 leading-zero count，不移动 magnitude。
  // v1.9 S5寄存e=A_raw-z；S6直接MAX，仍只做一次合并移位。
  dp_lzd #(
      .W(MAG_W)
  ) u_group_leading_detect (
      .in_magnitude(magnitude_d),
      .out_count   (z_d),
      .out_active  (magnitude_active)
  );
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] r5_special;
  wire [`DP_SPECIAL_W-1:0] lane0_special;
  wire [`DP_SPECIAL_W-1:0] lane1_special;
  wire signed [ANCHOR_W-1:0] anchor_d;
  wire signed [31:0] anchor_work;
  assign out_special = r5_special;
  wire [`DP_SPECIAL_W-1:0] merged_special;
  wire zero_scale_infinity;
  assign lane0_special = lane_group_special[0+:`DP_SPECIAL_W];
  assign lane1_special = lane_group_special[`DP_SPECIAL_W+:`DP_SPECIAL_W];
  assign merged_special = merge_special(lane0_special, lane1_special);
  assign zero_scale_infinity = (r4_scale_coefficient == 0) &
    (merged_special[`DP_SP_POS_INF] | merged_special[`DP_SP_NEG_INF]);
  assign special_d[`DP_SP_NAN] = merged_special[`DP_SP_NAN] | r4_scale_nan;
  assign special_d[`DP_SP_INVALID] = merged_special[`DP_SP_INVALID] | zero_scale_infinity;
  assign special_d[`DP_SP_POS_INF] = merged_special[`DP_SP_POS_INF] & ~zero_scale_infinity;
  assign special_d[`DP_SP_NEG_INF] = merged_special[`DP_SP_NEG_INF] & ~zero_scale_infinity;
  // [S5 指数坐标] A_raw = 元素公共指数 - 双 bias + scale 实指数 - F + (M-1)。
  // group_fraction 已计入系数乘法与补零；S6 不能再次扣除同一小数位数。
  // 零、特殊值的 anchor 为占位零，不参与浮点 MAX。
  // Q uses bias15 and F=LOCAL_W-2; E group coordinates remain unchanged.
  assign anchor_work = {{(32-(`DP_Q_EXP_W+1)){1'b0}}, lane_group_anchor[0]} -
                       ((r4_datatype < `DP_DT_MXFP4) ? 2*`DP_Q_BIAS : 0) -
                       ((r4_datatype < `DP_DT_MXFP4) ? LOCAL_W-2 :
                        (r4_datatype == `DP_DT_NVFP4) ? LOCAL_W-9 : LOCAL_W-7) +
                       MAG_W-1 + {{(32-`DP_PRODUCT_EXP_W){1'b0}}, r4_scale_exponent} - 2*`DP_SCALE_BIAS;
  assign anchor_d = (~magnitude_active | (special_d != 0)) ? 0 :
      (ARCHITECTURE_V19 != 0) ? r4_raw_anchor : anchor_work[ANCHOR_W-1:0];

  // [S5 寄存边界] 保存 scale/LZD 后的 group token；valid 与符号、幅值、anchor 同拍。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_out_valid (.clock(clock), .rst_n(rst_n), .in_d(r4_valid), .out_q(out_valid));
  dp_lib_DFFE #(.WIDTH(MAG_W))
  ff_s4_s5_out_magnitude (.clock(clock), .in_en(rst_n & r4_valid), .in_d(magnitude_d), .out_q(out_magnitude));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s4_s5_out_negative (.clock(clock), .in_en(rst_n & r4_valid), .in_d(negative_d), .out_q(out_negative));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_out_anchor (.clock(clock), .in_en(rst_n & r4_valid), .in_d(anchor_d), .out_q(out_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s4_s5_special (.clock(clock), .in_en(rst_n & r4_valid), .in_d(special_d), .out_q(r5_special));
  // verilog_format: on

  // S5 保存 compare_exp，供 S6 MAX 直接使用；out_z 仅为兼容观察。
  wire signed [ANCHOR_W-1:0] compare_exp_d;
  wire [ANCHOR_W-1:0] observed_zero_count;
  assign compare_exp_d = (magnitude_active & (special_d == 0)) ?
      anchor_d - $signed({{(ANCHOR_W-$clog2(MAG_W+1)){1'b0}}, z_d}) : 0;
  assign observed_zero_count = out_anchor - out_compare_exp;
  generate
    if (ARCHITECTURE_V19 != 0) begin : g_compare_register
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(ANCHOR_W))
      ff_s4_s5_compare_exp (.clock(clock), .in_en(rst_n & r4_valid), .in_d(compare_exp_d), .out_q(out_compare_exp));
      // verilog_format: on
      assign out_z = observed_zero_count[$clog2(MAG_W+1)-1:0];
    end else begin : g_legacy_z_register
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH($clog2(MAG_W + 1)))
      ff_s4_s5_out_z (.clock(clock), .in_en(rst_n & r4_valid), .in_d((special_d == 0) ? z_d : {$clog2(MAG_W+1){1'b0}}), .out_q(out_z));
      // verilog_format: on
      assign out_compare_exp = out_anchor - $signed({{(ANCHOR_W-$clog2(MAG_W+1)){1'b0}}, out_z});
    end
  endgenerate
endmodule
