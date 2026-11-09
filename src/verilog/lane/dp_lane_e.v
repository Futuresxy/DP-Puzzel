`include "dp_defs.vh"
// E8 lane: MXFP4/NVFP4/HiF4 only. S1 decode, S2 multiply/pair, S3 lane tree.
// v1.9 consumes e2 in S3 before the lane register; legacy E64 retains its S4 shift.
// Synchronous active-low reset clears valid; data holds through bubbles.
// TC widths include S; I excludes S. Product sign travels separately.
// Precision     | Input S | I | F | Product S | I | F | Pair S | I | F | Lane S | I | F
// ------------- | ------- | - | - | --------- | - | - | ------ | - | - | ------ | - | -
// MXFP4/NVFP4   | 0       | 3 | 1 | 0         | 6 | 2 | 1      | 7 | 2 | 1      | 9 | 2
// HiF4 (e1 in)  | 0       | 2 | 2 | 0         | 4 | 4 | 1      | 5 | 4 | 1      | 7 | 4
// All E after local lane shift: TC S1I9F4, 14 bits. No exponent MAX/right shifter.
// 阅读顺序 / 功能边界：
// S1 解包并保存幅值/符号；S2 八个 4x4 乘法 + 四个两项规约；S3 四项树。
// v1.9 在 S3 树后融合 e2，group 的 S4 寄存器捕获组和；legacy 保留原S4移位。
// 本模块仅保存 S1-S3；出口无额外 DFF，故不能把 S4 组合移位误算为新增周期。
module dp_lane_e #(
  // 静态迁移开关；0 保持独立 E64 的原流水，1 在 S3 消耗 e2。
  parameter integer ARCHITECTURE_V19 = 0
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
  output wire out_valid,
  output wire out_all_negative,
  output wire signed [13:0] out_sop
);
  localparam integer PRODUCT_W = 2 * `DP_MUL_LO;
  localparam integer PAIRS = `DP_E_LANES / 2;
  localparam integer PAIR_W = PRODUCT_W + 2;
  localparam integer LANE_W = PAIR_W + $clog2(PAIRS);
  localparam integer FUSED_W = LANE_W + `DP_E_GUARD;
  wire [2:0] valid_q;
  wire [`DP_E_LANES*`DP_MUL_LO-1:0] a_mantissa_s1_q;
  wire [`DP_E_LANES*`DP_MUL_LO-1:0] b_mantissa_s1_q;
  wire [`DP_E_LANES-1:0] a_sign_s1_q;
  wire [`DP_E_LANES-1:0] b_sign_s1_q;
  wire [1:0] shift_s1_q;
  wire [1:0] shift_s2_q;
  wire [1:0] shift_s3_q;
  wire [PAIRS*PAIR_W-1:0] pairs_s2_q;
  wire all_negative_s2_q;
  wire all_negative_s3_q;
  wire signed [LANE_W-1:0] sop_s3_q;
  wire [`DP_E_LANES*`DP_MUL_LO-1:0] a_mantissa_d;
  wire [`DP_E_LANES*`DP_MUL_LO-1:0] b_mantissa_d;
  wire [`DP_E_LANES-1:0] product_negative;
  wire [`DP_E_LANES*(PRODUCT_W+1)-1:0] signed_products;
  wire [PAIRS*PAIR_W-1:0] pairs_d;
  wire signed [LANE_W-1:0] lane_sum_d;
  // Dedicated operand decoders; S1 registers remain owned by this lane.
  wire [`DP_E_LANES-1:0] a_sign_d;
  wire [`DP_E_LANES-1:0] b_sign_d;
  dp_lane_unpack_e u_operand_unpack_a (
    .in_data(in_a),
    .in_datatype(in_datatype),
    .in_e1(in_e1_a),
    .out_magnitude(a_mantissa_d),
    .out_negative(a_sign_d)
  );
  dp_lane_unpack_e u_operand_unpack_b (
    .in_data(in_b),
    .in_datatype(in_datatype),
    .in_e1(in_e1_b),
    .out_magnitude(b_mantissa_d),
    .out_negative(b_sign_d)
  );

  // [S1 寄存边界] 保存 E 解包幅值/符号和 e2 移位量；valid 每拍推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(in_valid), .out_q(valid_q[0]));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s0_s1_a_sign_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(a_sign_d), .out_q(a_sign_s1_q));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES))
  ff_s0_s1_b_sign_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(b_sign_d), .out_q(b_sign_s1_q));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES * `DP_MUL_LO))
  ff_s0_s1_a_mantissa_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(a_mantissa_d), .out_q(a_mantissa_s1_q));
  dp_lib_DFFE #(.WIDTH(`DP_E_LANES * `DP_MUL_LO))
  ff_s0_s1_b_mantissa_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(b_mantissa_d), .out_q(b_mantissa_s1_q));
  dp_lib_DFFE #(.WIDTH((1) - (0) + 1))
  ff_s0_s1_shift_s1 (.clock(clock), .in_en(rst_n & in_valid), .in_d(in_datatype == `DP_DT_HIF4 ? {1'b0, in_e2_a} + {1'b0, in_e2_b} : 2'd2), .out_q(shift_s1_q));
  // verilog_format: on

  // [S2 乘积] 4 位幅值乘法得到 unsigned8；符号异或后用 signed9 容器恢复补码。
  // 随后的 u_pair_sum 为第一层规约，S2 只保存四个 signed10 pair，减少乘积寄存位。
  genvar element_index;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_product
      wire [PRODUCT_W-1:0] magnitude;
      wire signed [PRODUCT_W:0] positive_product;
      assign positive_product = {1'b0, magnitude};
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_LO)
      ) u_element_mul (
        .in_a(a_mantissa_s1_q[element_index*`DP_MUL_LO+:`DP_MUL_LO]),
        .in_b(b_mantissa_s1_q[element_index*`DP_MUL_LO+:`DP_MUL_LO]),
        .out_product(magnitude)
      );
      assign
        product_negative[element_index] = a_sign_s1_q[element_index] ^ b_sign_s1_q[element_index];
      assign signed_products[element_index*(PRODUCT_W+1)+:PRODUCT_W+1] =
        product_negative[element_index] ? -positive_product : positive_product;
    end
    for (element_index = 0; element_index < PAIRS; element_index = element_index + 1) begin : g_pair
      wire signed [PRODUCT_W:0] pair_left;
      assign pair_left = signed_products[2*element_index*(PRODUCT_W+1)+:PRODUCT_W+1];
      wire signed [PRODUCT_W:0] pair_right;
      assign pair_right = signed_products[(2*element_index+1)*(PRODUCT_W+1)+:PRODUCT_W+1];
      // S2 第一层规约：两个 signed9 乘积 -> signed10 pair，显式保留进位。
      // N=2 的 dp_sum_tree 是单层加法器，没有寄存器；S2 DFF 在父层保存结果。
      dp_sum_tree #(
        .N(2),
        .W(PRODUCT_W + 1)
      ) u_pair_sum (
        .in_values({pair_right, pair_left}),
        .out_sum  (pairs_d[element_index*PAIR_W+:PAIR_W])
      );
    end
  endgenerate

  // [S2 寄存边界] 保存四个 pair 及符号摘要、移位量；不保存八个完整乘积。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[0]), .out_q(valid_q[1]));
  dp_lib_DFFE #(.WIDTH(PAIRS * PAIR_W))
  ff_s1_s2_pairs_s2 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(pairs_d), .out_q(pairs_s2_q));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_all_negative_s2 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(&product_negative), .out_q(all_negative_s2_q));
  dp_lib_DFFE #(.WIDTH((1) - (0) + 1))
  ff_s1_s2_shift_s2 (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(shift_s1_q), .out_q(shift_s2_q));
  // verilog_format: on

  // [S3 lane 累加树] 四个 signed10 pair 经两层树得到 signed12。
  // 此处不做右移和舍入；HiF4 的 e1 已在解包中融合，e2 在窄树后精确左移。
  dp_sum_tree #(
    .N(PAIRS),
    .W(PAIR_W)
  ) u_lane_sop_tree (
    .in_values(pairs_s2_q),
    .out_sum  (lane_sum_d)
  );

  // [S3 寄存边界] v1.9 先在窄 S14 容器内融合 e2，再寄存；不再传递 e2。
  // MX/NV 固定左移 2，将 F2 转为 F4；HiF4 左移 e2_a+e2_b，保留完整精度。
  // legacy 分支仅供独立 E64 回放，两种实现均保持输入至 group S5 的总延迟。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[1]), .out_q(valid_q[2]));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_all_negative_s3 (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(all_negative_s2_q), .out_q(all_negative_s3_q));
  // verilog_format: on
  generate
    if (ARCHITECTURE_V19 != 0) begin : g_v19
      // 两层树的 S12 和先符号扩位，最多左移 2，输出 S1I9F4。
      wire signed [FUSED_W-1:0] lane_fused_d;
      wire signed [FUSED_W-1:0] r3_fused_sum;
      dp_lane_e_shift #(
        .IN_W     (LANE_W),
        .OUT_W    (FUSED_W)
      ) u_lane_coordinate_shift (
        .in_sum   (lane_sum_d),
        .in_shift (shift_s2_q),
        .out_sum  (lane_fused_d)
      );
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(FUSED_W))
      ff_s2_s3_fused_sum (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(lane_fused_d), .out_q(r3_fused_sum));
      // verilog_format: on
      assign out_sop = r3_fused_sum;
      // 旧观察线不产生寄存器；新验证使用 r3_fused_sum。
      assign sop_s3_q = {LANE_W{1'b0}};
      assign shift_s3_q = {`DP_E_GUARD{1'b0}};
    end else begin : g_legacy
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(LANE_W))
      ff_s2_s3_sop (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(lane_sum_d), .out_q(sop_s3_q));
      dp_lib_DFFE #(.WIDTH(`DP_E_GUARD))
      ff_s2_s3_shift (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(shift_s2_q), .out_q(shift_s3_q));
      // verilog_format: on
      dp_lane_e_shift #(
        .IN_W     (LANE_W),
        .OUT_W    (FUSED_W)
      ) u_lane_coordinate_shift (
        .in_sum   (sop_s3_q),
        .in_shift (shift_s3_q),
        .out_sum  (out_sop)
      );
    end
  endgenerate
  assign out_valid = valid_q[2];
  assign out_all_negative = all_negative_s3_q;
endmodule
