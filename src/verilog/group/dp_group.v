`include "dp_defs.vh"
// T2H4Q8E16: two synchronized lanes, S2 common MAX, S5 abs/scale/LZD.
// Owns S1 scale decode and S2 scale-pair arithmetic; transport stops at S4.
// v1.8 output: unnormalized magnitude, A_raw and registered compare_exp=A_raw-z.
// BASELINE_V18=0 retains the old z-register contract for unmigrated tops.
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
// TF32               | 1 | 3  | P+2
// FP16 / BF16        | 1 | 4  | P+1
// MXFP8 / MXFP6      | 1 | 5  | P
// MXFP4              | 1 | 10 | P-5
// NVFP4              | 1 | 12 | P-7
// HiF4 legacy        | 1 | 10 | P-5
// HiF4 v1.8          | 1 | 12 | P-7
// INT8               | 1 | 18 | P-13
// LZD reads the listed I/F as unsigned magnitude (S=0).
// 阅读顺序 / 功能边界：
// 数据主路：两个多精度 lane -> S5 两项树/abs -> scale 或旁路/LZD -> token。
// 旁带：S1 scale 解包，S2 系数积/指数和，再延迟到 S5；S2 公共 MAX 回送两 lane。
// 两个 lane 共享 valid 和时钟，没有独立握手；MAX 只产生共同坐标，不等待 lane 结果。
module dp_group #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  // 仅 dp_top 本轮迁移；旧混合顶层保留默认的 v1.7 数值边界。
  parameter integer BASELINE_V18 = 0,
  parameter integer LANE_SOP_W = LOCAL_W + 1 + $clog2(`DP_Q_LANES),
  parameter integer GROUP_W = LANE_SOP_W + $clog2(`DP_LANES),
  parameter integer MAG_W = GROUP_W - 1,
  parameter integer ANCHOR_W = anchor_width(MAG_W)
) (
  input wire clock,
  input wire rst_n,
  input wire in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_a,
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_b,
  input wire [`DP_SCALE_W-1:0] in_scale_a,
  input wire [`DP_SCALE_W-1:0] in_scale_b,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_datatype,
  input wire [3:0] in_e1_a,
  input wire [3:0] in_e1_b,
  input wire [1:0] in_e2_a,
  input wire [1:0] in_e2_b,
  output wire out_valid,
  output wire out_negative,
  output wire [MAG_W-1:0] out_magnitude,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  // v1.8 S5 寄存 MAX 键 A_raw-z；原幅值不移动，anchor 仍是物理 MSB 坐标。
  output wire signed [ANCHOR_W-1:0] out_compare_exp,
  output wire [$clog2(MAG_W+1)-1:0] out_z,
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar lane_index;

  `include "dp_functions.vh"
  localparam integer COEFF_W = 2 * `DP_SCALE_M;
  localparam integer SCALE_MAG_W = `DP_SCALE_SOP_W - 1;
  localparam integer STRUCTURAL_DROP = GROUP_W - `DP_SCALE_SOP_W;
  localparam integer SCALE_PRODUCT_W = SCALE_MAG_W + COEFF_W;
  localparam integer SCALE_LOW_PAD = MAG_W - SCALE_PRODUCT_W;
  wire [3:0] valid_q;
  wire [`DP_TYPE_W-1:0] type_q[0:3];
  wire [`DP_LANES*LANE_SOP_W-1:0] lane_group_sum;
  wire [`DP_LANES*(`DP_PRODUCT_EXP_W+1)-1:0] lane_exponent_max_candidates;
  wire [`DP_LANES-1:0] lane_exponent_max_active;
  wire [`DP_LANES-1:0] lane_group_all_negative;
  wire [`DP_LANES-1:0] lane_group_valid;
  wire [`DP_LANES*`DP_SPECIAL_W-1:0] lane_group_special;
  wire [`DP_PRODUCT_EXP_W-1:0] lane_group_anchor[0:`DP_LANES-1];
  wire signed [`DP_PRODUCT_EXP_W:0] exponent_max_lane_anchor;
  wire max_active;
  // [lane 分发] 每 lane 接收连续 32 位 A/B 切片和对应 HiF4 e1/e2。
  // 同一 group 的 scale 在父层只解包一份 A 和一份 B，由两个 lane 的合并结果共用。
  generate
    for (lane_index = 0; lane_index < `DP_LANES; lane_index = lane_index + 1) begin : g_lane
      wire [`DP_PRODUCT_EXP_W-1:0] candidate;
      wire [`DP_SPECIAL_W-1:0] special_value;
      dp_lane #(
        .LOCAL_W(LOCAL_W),
        .BASELINE_V18(BASELINE_V18)
      ) u_lane (
        .clock(clock),
        .rst_n(rst_n),
        .in_valid(in_valid),
        .in_datatype(in_datatype),
        .in_a(in_a[lane_index*`DP_LANE_W+:`DP_LANE_W]),
        .in_b(in_b[lane_index*`DP_LANE_W+:`DP_LANE_W]),
        .in_e1_a(in_e1_a[lane_index*2+:2]),
        .in_e1_b(in_e1_b[lane_index*2+:2]),
        .in_e2_a(in_e2_a[lane_index]),
        .in_e2_b(in_e2_b[lane_index]),
        .out_candidate(candidate),
        .out_candidate_active(lane_exponent_max_active[lane_index]),
        .in_group_max(exponent_max_lane_anchor[`DP_PRODUCT_EXP_W-1:0]),
        .out_valid(lane_group_valid[lane_index]),
        .out_sop(lane_group_sum[lane_index*LANE_SOP_W+:LANE_SOP_W]),
        .out_anchor(lane_group_anchor[lane_index]),
        .out_special(special_value),
        .out_all_negative(lane_group_all_negative[lane_index])
      );
      assign lane_exponent_max_candidates[lane_index*(`DP_PRODUCT_EXP_W+1)+:`DP_PRODUCT_EXP_W+1] = {
        1'b0, candidate
      };
      assign lane_group_special[lane_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] = special_value;
    end
  endgenerate
  // [S2 公共 MAX] 从两 lane 的有限非零候选选同一个原始指数和。
  // 该组合值在各 lane 的 S2 DFF 捕获，与乘积同时到达；并非跨事务反馈环。
  dp_max_tree #(
    .N(`DP_LANES),
    .W(`DP_PRODUCT_EXP_W + 1)
  ) u_group_exponent_max (
    .in_values(lane_exponent_max_candidates),
    .in_active(lane_exponent_max_active),
    .out_max(exponent_max_lane_anchor),
    .out_active(max_active)
  );
  wire [`DP_SCALE_M-1:0] scale_a_magnitude_d;
  wire [`DP_SCALE_M-1:0] scale_b_magnitude_d;
  wire [`DP_EXP_W-1:0] scale_a_exponent_d;
  wire [`DP_EXP_W-1:0] scale_b_exponent_d;
  wire scale_a_nan_d;
  wire scale_b_nan_d;
  wire [`DP_SCALE_M-1:0] scale_a_magnitude_q;
  wire [`DP_SCALE_M-1:0] scale_b_magnitude_q;
  wire [`DP_EXP_W-1:0] scale_a_exponent_q;
  wire [`DP_EXP_W-1:0] scale_b_exponent_q;
  wire nan_s1_q;
  wire [COEFF_W-1:0] coeff_d;
  wire [COEFF_W-1:0] coeff_q[1:3];
  wire [`DP_PRODUCT_EXP_W-1:0] scale_exp_q[1:3];
  wire scale_nan_q[1:3];
  // [scale S1 -> S2] I1F3 幅值；v1.8 指数是 signed8 无偏值，legacy 保留 bias=127。
  // S2 尾数相乘形成 I2F6 系数，同时指数相加；NaN 分类独立传递，不靠零幅值推断。
  dp_scale_unpack #(.UNBIASED_EXPONENT(BASELINE_V18)) u_scale_unpack_a (
    .in_data(in_scale_a),
    .in_datatype(in_scale_datatype),
    .out_magnitude(scale_a_magnitude_d),
    .out_exponent(scale_a_exponent_d),
    .out_nan(scale_a_nan_d)
  );
  dp_scale_unpack #(.UNBIASED_EXPONENT(BASELINE_V18)) u_scale_unpack_b (
    .in_data(in_scale_b),
    .in_datatype(in_scale_datatype),
    .out_magnitude(scale_b_magnitude_d),
    .out_exponent(scale_b_exponent_d),
    .out_nan(scale_b_nan_d)
  );

  // [S1 寄存边界] 保存 scale 解包值、类型和 valid，供下一段系数预乘使用。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(in_valid), .out_q(valid_q[0]));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s0_s1_type_q_0 (.clock(clock), .in_en(rst_n & in_valid), .in_d(in_datatype), .out_q(type_q[0]));
  dp_lib_DFFE #(.WIDTH(`DP_SCALE_M))
  ff_s0_s1_sa (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_magnitude_d), .out_q(scale_a_magnitude_q));
  dp_lib_DFFE #(.WIDTH(`DP_SCALE_M))
  ff_s0_s1_sb (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_b_magnitude_d), .out_q(scale_b_magnitude_q));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_ea (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_exponent_d), .out_q(scale_a_exponent_q));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_eb (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_b_exponent_d), .out_q(scale_b_exponent_q));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s0_s1_nan_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(scale_a_nan_d | scale_b_nan_d), .out_q(nan_s1_q));
  // verilog_format: on

  dp_mul_unsigned #(
    .A_W(`DP_SCALE_M),
    .B_W(`DP_SCALE_M)
  ) u_scale_pair_mul (
    .in_a(scale_a_magnitude_q),
    .in_b(scale_b_magnitude_q),
    .out_product(coeff_d)
  );

  // signed8 的去偏指数先符号扩展，再形成 signed9 的 S2 和。
  wire [`DP_PRODUCT_EXP_W-1:0] scale_exponent_sum_d;
  assign scale_exponent_sum_d = (BASELINE_V18 != 0) ?
      {scale_a_exponent_q[`DP_EXP_W-1], scale_a_exponent_q} + {scale_b_exponent_q[`DP_EXP_W-1], scale_b_exponent_q} :
      {1'b0, scale_a_exponent_q} + {1'b0, scale_b_exponent_q};
  // S2 group MAX 保存供 S3 提前算 anchor；E 候选已由 lane 排除，值为0。
  wire [`DP_PRODUCT_EXP_W-1:0] r2_group_max;
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s1_s2_group_max (.clock(clock), .in_en(rst_n & valid_q[0] & (BASELINE_V18 != 0)), .in_d(exponent_max_lane_anchor[`DP_PRODUCT_EXP_W-1:0]), .out_q(r2_group_max));
  // verilog_format: on

  // [S2 寄存边界] 保存 scale 系数积/指数和；两 lane 在内部捕获共同 MAX。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[0]), .out_q(valid_q[1]));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s1_s2_type_q_1 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(type_q[0]), .out_q(type_q[1]));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s1_s2_coeff_q_1 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(coeff_d), .out_q(coeff_q[1]));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s1_s2_scale_exp_q_1 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(scale_exponent_sum_d), .out_q(scale_exp_q[1]));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_scale_nan_q_1 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(nan_s1_q), .out_q(scale_nan_q[1]));
  // verilog_format: on

  // [S3 anchor] 模式常量 M-1-F-2*bias 与已去偏的 scale 指数和合并。
  // HiF4 的 e2 在 lane 内消耗，F 与 NVFP4 相同；不再扣除 254。
  wire signed [31:0] raw_anchor_work;
  wire signed [ANCHOR_W-1:0] r3_raw_anchor;
  wire signed [ANCHOR_W-1:0] r4_raw_anchor;
  assign raw_anchor_work = $signed({{(32-`DP_PRODUCT_EXP_W){1'b0}}, r2_group_max}) +
      ((scale_type(type_q[1]) != `DP_SC_NONE) ? $signed({{(32-`DP_PRODUCT_EXP_W){scale_exp_q[1][`DP_PRODUCT_EXP_W-1]}}, scale_exp_q[1]}) : 0) +
      MAG_W - 1 - group_fraction((type_q[1] == `DP_DT_HIF4) ? `DP_DT_NVFP4 : type_q[1], LOCAL_W) - 2 * element_bias(type_q[1]);
  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s2_s3_raw_anchor (.clock(clock), .in_en(rst_n & valid_q[1] & (BASELINE_V18 != 0)), .in_d(raw_anchor_work[ANCHOR_W-1:0]), .out_q(r3_raw_anchor));
  // verilog_format: on

  // [S3 寄存边界] scale 系数与分类保持并延迟一拍，与 lane 的 S3 对齐同行。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[1]), .out_q(valid_q[2]));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s2_s3_type_q_2 (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(type_q[1]), .out_q(type_q[2]));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s2_s3_coeff_q_2 (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(coeff_q[1]), .out_q(coeff_q[2]));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s2_s3_scale_exp_q_2 (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(scale_exp_q[1]), .out_q(scale_exp_q[2]));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_scale_nan_q_2 (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(scale_nan_q[1]), .out_q(scale_nan_q[2]));
  // verilog_format: on

  // verilog_format: off
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s3_s4_raw_anchor (.clock(clock), .in_en(rst_n & valid_q[2] & (BASELINE_V18 != 0)), .in_d(r3_raw_anchor), .out_q(r4_raw_anchor));
  // verilog_format: on

  // [S4 寄存边界] scale 旁带继续延迟，与两个 lane 的 S4 和同拍到达 S5。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[2]), .out_q(valid_q[3]));
  dp_lib_DFFE #(.WIDTH(`DP_TYPE_W))
  ff_s3_s4_type_q_3 (.clock(clock), .in_en(rst_n & valid_q[2]), .in_d(type_q[2]), .out_q(type_q[3]));
  dp_lib_DFFE #(.WIDTH(COEFF_W))
  ff_s3_s4_coeff_q_3 (.clock(clock), .in_en(rst_n & valid_q[2]), .in_d(coeff_q[2]), .out_q(coeff_q[3]));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s3_s4_scale_exp_q_3 (.clock(clock), .in_en(rst_n & valid_q[2]), .in_d(scale_exp_q[2]), .out_q(scale_exp_q[3]));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s3_s4_scale_nan_q_3 (.clock(clock), .in_en(rst_n & valid_q[2]), .in_d(scale_nan_q[2]), .out_q(scale_nan_q[3]));
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
  assign inject_scale = (type_q[3] == `DP_DT_NVFP4 | type_q[3] == `DP_DT_HIF4) & valid_q[3];
  // Both branches share the absolute value. NV/HiF compact the magnitude
  // by slicing off structural low zeros; their legal group sums fit SCALE_MAG_W.
  wire group_negative;
  assign group_negative = group_sum[GROUP_W-1];
  wire [GROUP_W-1:0] absolute_sop;
  assign absolute_sop = group_negative ? -group_sum : group_sum;
  wire [SCALE_MAG_W-1:0] compact_mag;
  assign compact_mag = inject_scale ? absolute_sop[STRUCTURAL_DROP+:SCALE_MAG_W] : 0;
  wire [COEFF_W-1:0] compact_coeff;
  assign compact_coeff = inject_scale ? coeff_q[3] : 0;
  wire [SCALE_PRODUCT_W-1:0] scale_product;
  // [S5 scale 注入] 仅 NVFP4/HiF4 启用 14x8 无符号乘法，22 位输出完整保留。
  // 旁路和乘法结果都补零放入同宽 S5 magnitude 容器；MX 的 2^scale 由 anchor 表达。
  dp_scale_multiply u_group_scale_mul (
    .in_magnitude(compact_mag),
    .in_coefficient(compact_coeff),
    .out_product(scale_product)
  );
  wire [MAG_W-1:0] magnitude_d;
  assign
    magnitude_d = inject_scale ? {scale_product, {SCALE_LOW_PAD{1'b0}}} : absolute_sop[MAG_W-1:0];
  wire negative_d;
  assign negative_d = group_negative | (group_sum == 0 & (&lane_group_all_negative));
  wire [$clog2(MAG_W+1)-1:0] z_d;
  wire magnitude_active;
  // [S5 LZD] 只检测补零后幅值的 leading-zero count，不移动 magnitude。
  // v1.8 本级计算并保存 A_raw-z，S6 直接比较；幅值留在原坐标，不在这里移位。
  dp_lzd #(
    .W(MAG_W)
  ) u_group_leading_detect (
    .in_magnitude(magnitude_d),
    .out_count(z_d),
    .out_active(magnitude_active)
  );
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] special_q;
  wire [`DP_SPECIAL_W-1:0] lane0_special;
  wire [`DP_SPECIAL_W-1:0] lane1_special;
  wire signed [ANCHOR_W-1:0] anchor_d;
  wire signed [31:0] anchor_work;
  assign out_special = special_q;
  wire [`DP_SPECIAL_W-1:0] merged_special;
  wire zero_scale_infinity;
  assign lane0_special = lane_group_special[0+:`DP_SPECIAL_W];
  assign lane1_special = lane_group_special[`DP_SPECIAL_W+:`DP_SPECIAL_W];
  assign merged_special = merge_special(lane0_special, lane1_special);
  assign zero_scale_infinity = (coeff_q[3] == 0) &
    (merged_special[`DP_SP_POS_INF] | merged_special[`DP_SP_NEG_INF]);
  assign special_d[`DP_SP_NAN] = merged_special[`DP_SP_NAN] | scale_nan_q[3];
  assign special_d[`DP_SP_INVALID] = merged_special[`DP_SP_INVALID] | zero_scale_infinity;
  assign special_d[`DP_SP_POS_INF] = merged_special[`DP_SP_POS_INF] & ~zero_scale_infinity;
  assign special_d[`DP_SP_NEG_INF] = merged_special[`DP_SP_NEG_INF] & ~zero_scale_infinity;
  // [legacy S5 指数坐标] 仅 BASELINE_V18=0 使用下列旧式计算；v1.8 选择 r4_raw_anchor。
  // A_raw = 元素公共指数 - 双 bias + scale 实指数 - F + (M-1)。
  // group_fraction 已计入系数乘法与补零；S6 不能再次扣除同一小数位数。
  // 零、特殊值、INT8 的 anchor 为占位零，不参与浮点 MAX。
  assign anchor_work = {{(32 - `DP_PRODUCT_EXP_W) {1'b0}}, lane_group_anchor[0]} - 2 * element_bias(
    type_q[3]
  ) - group_fraction(
    type_q[3], LOCAL_W
  ) + MAG_W - 1 + (scale_type(
    type_q[3]
  ) != `DP_SC_NONE ? {{(32 - `DP_PRODUCT_EXP_W) {1'b0}}, scale_exp_q[3]} - 2 * `DP_SCALE_BIAS : 0);
  assign anchor_d = (~magnitude_active | (special_d != 0) | (type_q[3] == `DP_DT_INT8)) ? 0 :
    ((BASELINE_V18 != 0) ? r4_raw_anchor : anchor_work[ANCHOR_W-1:0]);

  // [S5 寄存边界] 保存 scale/LZD 后的 group token；valid 与符号、幅值、anchor 同拍。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_out_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[3]), .out_q(out_valid));
  dp_lib_DFFE #(.WIDTH(MAG_W))
  ff_s4_s5_out_magnitude (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(magnitude_d), .out_q(out_magnitude));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s4_s5_out_negative (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(negative_d), .out_q(out_negative));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_out_anchor (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(anchor_d), .out_q(out_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s4_s5_special (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(special_d), .out_q(special_q));

  // verilog_format: on

  // S5: e=A_raw-z 直接作为后端 MAX 键保存；z 只作兼容观察，不另加寄存器。
  wire signed [ANCHOR_W-1:0] compare_exp_d;
  wire [ANCHOR_W-1:0] observed_z;
  assign compare_exp_d = (magnitude_active & (special_d == 0) & (type_q[3] != `DP_DT_INT8)) ?
      anchor_d - $signed({{(ANCHOR_W-$clog2(MAG_W+1)){1'b0}}, z_d}) : 0;
  assign observed_z = out_anchor - out_compare_exp;
  generate
    if (BASELINE_V18 != 0) begin : g_compare_register
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(ANCHOR_W))
      ff_s4_s5_compare_exp (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(compare_exp_d), .out_q(out_compare_exp));
      // verilog_format: on
      assign out_z = observed_z[$clog2(MAG_W+1)-1:0];
    end else begin : g_legacy_z_register
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH($clog2(MAG_W + 1)))
      ff_s4_s5_out_z (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(((special_d == 0) & (type_q[3] != `DP_DT_INT8)) ? z_d : {$clog2(MAG_W+1){1'b0}}), .out_q(out_z));
      // verilog_format: on
      assign out_compare_exp = out_anchor - $signed({{(ANCHOR_W-$clog2(MAG_W+1)){1'b0}}, out_z});
    end
  endgenerate
endmodule
