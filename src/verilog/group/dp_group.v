`include "dp_defs.vh"
// T2H4Q8E16: two synchronized lanes, S2 common MAX, S5 abs/scale/LZD.
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
// TF32               | 1 | 3  | P+2
// FP16 / BF16        | 1 | 4  | P+1
// MXFP8 / MXFP6      | 1 | 5  | P
// MXFP4              | 1 | 10 | P-5
// NVFP4              | 1 | 12 | P-7
// HiF4               | 1 | 10 | P-5
// INT8               | 1 | 18 | P-13
// LZD reads the listed I/F as unsigned magnitude (S=0).
module dp_group #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
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
  generate
    for (lane_index = 0; lane_index < `DP_LANES; lane_index = lane_index + 1) begin : g_lane
      wire [`DP_PRODUCT_EXP_W-1:0] candidate;
      wire [`DP_SPECIAL_W-1:0] special_value;
      dp_lane #(
        .LOCAL_W(LOCAL_W)
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
  dp_scale_unpack u_scale_unpack_a (
    .in_data(in_scale_a),
    .in_datatype(in_scale_datatype),
    .out_magnitude(scale_a_magnitude_d),
    .out_exponent(scale_a_exponent_d),
    .out_nan(scale_a_nan_d)
  );
  dp_scale_unpack u_scale_unpack_b (
    .in_data(in_scale_b),
    .in_datatype(in_scale_datatype),
    .out_magnitude(scale_b_magnitude_d),
    .out_exponent(scale_b_exponent_d),
    .out_nan(scale_b_nan_d)
  );
  dp_mul_unsigned #(
    .A_W(`DP_SCALE_M),
    .B_W(`DP_SCALE_M)
  ) u_scale_pair_mul (
    .in_a(scale_a_magnitude_q),
    .in_b(scale_b_magnitude_q),
    .out_product(coeff_d)
  );
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
  assign anchor_work = {{(32 - `DP_PRODUCT_EXP_W) {1'b0}}, lane_group_anchor[0]} - 2 * element_bias(
    type_q[3]
  ) - group_fraction(
    type_q[3], LOCAL_W
  ) + MAG_W - 1 + (scale_type(
    type_q[3]
  ) != `DP_SC_NONE ? {{(32 - `DP_PRODUCT_EXP_W) {1'b0}}, scale_exp_q[3]} - 2 * `DP_SCALE_BIAS : 0);
  assign anchor_d = (~magnitude_active | (special_d != 0) | (type_q[3] == `DP_DT_INT8)) ? 0 :
    anchor_work[ANCHOR_W-1:0];

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
  // S4 -> S5: out_valid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s4_s5_out_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (valid_q[3]),
    .out_q(out_valid)
  );
  // S0 -> S1: type_q_0.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s0_s1_type_q_0 (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (in_datatype),
    .out_q(type_q[0])
  );
  // S1 -> S2: type_q_1.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s1_s2_type_q_1 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (type_q[0]),
    .out_q(type_q[1])
  );
  // S2 -> S3: type_q_2.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s2_s3_type_q_2 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (type_q[1]),
    .out_q(type_q[2])
  );
  // S3 -> S4: type_q_3.
  dp_lib_DFFE #(
    .WIDTH(`DP_TYPE_W)
  ) ff_s3_s4_type_q_3 (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (type_q[2]),
    .out_q(type_q[3])
  );
  // S0 -> S1: sa.
  dp_lib_DFFE #(
    .WIDTH(`DP_SCALE_M)
  ) ff_s0_s1_sa (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (scale_a_magnitude_d),
    .out_q(scale_a_magnitude_q)
  );
  // S0 -> S1: sb.
  dp_lib_DFFE #(
    .WIDTH(`DP_SCALE_M)
  ) ff_s0_s1_sb (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (scale_b_magnitude_d),
    .out_q(scale_b_magnitude_q)
  );
  // S0 -> S1: ea.
  dp_lib_DFFE #(
    .WIDTH(`DP_EXP_W)
  ) ff_s0_s1_ea (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (scale_a_exponent_d),
    .out_q(scale_a_exponent_q)
  );
  // S0 -> S1: eb.
  dp_lib_DFFE #(
    .WIDTH(`DP_EXP_W)
  ) ff_s0_s1_eb (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (scale_b_exponent_d),
    .out_q(scale_b_exponent_q)
  );
  // S0 -> S1: nan_s1.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s0_s1_nan_s1 (
    .clock(clock),
    .in_en(rst_n & in_valid),
    .in_d (scale_a_nan_d | scale_b_nan_d),
    .out_q(nan_s1_q)
  );
  // S1 -> S2: coeff_q_1.
  dp_lib_DFFE #(
    .WIDTH(COEFF_W)
  ) ff_s1_s2_coeff_q_1 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (coeff_d),
    .out_q(coeff_q[1])
  );
  // S1 -> S2: scale_exp_q_1.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s1_s2_scale_exp_q_1 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d ({1'b0, scale_a_exponent_q} + {1'b0, scale_b_exponent_q}),
    .out_q(scale_exp_q[1])
  );
  // S1 -> S2: scale_nan_q_1.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s1_s2_scale_nan_q_1 (
    .clock(clock),
    .in_en(rst_n & valid_q[0]),
    .in_d (nan_s1_q),
    .out_q(scale_nan_q[1])
  );
  // S2 -> S3: coeff_q_2.
  dp_lib_DFFE #(
    .WIDTH(COEFF_W)
  ) ff_s2_s3_coeff_q_2 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (coeff_q[1]),
    .out_q(coeff_q[2])
  );
  // S2 -> S3: scale_exp_q_2.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s2_s3_scale_exp_q_2 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (scale_exp_q[1]),
    .out_q(scale_exp_q[2])
  );
  // S2 -> S3: scale_nan_q_2.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s2_s3_scale_nan_q_2 (
    .clock(clock),
    .in_en(rst_n & valid_q[1]),
    .in_d (scale_nan_q[1]),
    .out_q(scale_nan_q[2])
  );
  // S3 -> S4: coeff_q_3.
  dp_lib_DFFE #(
    .WIDTH(COEFF_W)
  ) ff_s3_s4_coeff_q_3 (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (coeff_q[2]),
    .out_q(coeff_q[3])
  );
  // S3 -> S4: scale_exp_q_3.
  dp_lib_DFFE #(
    .WIDTH(`DP_PRODUCT_EXP_W)
  ) ff_s3_s4_scale_exp_q_3 (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (scale_exp_q[2]),
    .out_q(scale_exp_q[3])
  );
  // S3 -> S4: scale_nan_q_3.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s3_s4_scale_nan_q_3 (
    .clock(clock),
    .in_en(rst_n & valid_q[2]),
    .in_d (scale_nan_q[2]),
    .out_q(scale_nan_q[3])
  );
  // S4 -> S5: out_magnitude.
  dp_lib_DFFE #(
    .WIDTH(MAG_W)
  ) ff_s4_s5_out_magnitude (
    .clock(clock),
    .in_en(rst_n & valid_q[3]),
    .in_d (magnitude_d),
    .out_q(out_magnitude)
  );
  // S4 -> S5: out_negative.
  dp_lib_DFFE #(
    .WIDTH(1)
  ) ff_s4_s5_out_negative (
    .clock(clock),
    .in_en(rst_n & valid_q[3]),
    .in_d (negative_d),
    .out_q(out_negative)
  );
  // S4 -> S5: out_anchor.
  dp_lib_DFFE #(
    .WIDTH(ANCHOR_W)
  ) ff_s4_s5_out_anchor (
    .clock(clock),
    .in_en(rst_n & valid_q[3]),
    .in_d (anchor_d),
    .out_q(out_anchor)
  );
  // S4 -> S5: special.
  dp_lib_DFFE #(
    .WIDTH(`DP_SPECIAL_W)
  ) ff_s4_s5_special (
    .clock(clock),
    .in_en(rst_n & valid_q[3]),
    .in_d (special_d),
    .out_q(special_q)
  );
  // S4 -> S5: out_z.
  dp_lib_DFFE #(
    .WIDTH($clog2(MAG_W + 1))
  ) ff_s4_s5_out_z (
    .clock(clock),
    .in_en(rst_n & valid_q[3]),
    .in_d (((special_d == 0) & (type_q[3] != `DP_DT_INT8)) ? z_d : 0),
    .out_q(out_z)
  );
endmodule
