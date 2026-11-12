`include "dp_defs.vh"
// Q8 group, two Q4 lanes. S2 common MAX; S3 A_raw; S5 sum/abs/LZD/token.
// Supports only MXFP8/6 with E8M0 scale. No scale coefficient multiplier or E logic.
// Same S5 token fields/cycle as v1.9 groups; II=1, synchronous low reset.
// S5 separate sign plus magnitude S0I5F(LOCAL_W-2), default U31.
module dp_group_q #(
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
  output wire out_valid,
  output wire out_negative,
  output wire [MAG_W-1:0] out_magnitude,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  output wire signed [ANCHOR_W-1:0] out_compare_exp,
  output wire [$clog2(MAG_W+1)-1:0] out_z,
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  `include "dp_functions.vh"
  // Default Q A_raw = common biased product exponent + scale exponent - 26.
  localparam integer Q_ANCHOR_OFFSET = MAG_W-1-(LOCAL_W-2)-2*`DP_Q_BIAS;
  wire q_request;
  wire r1_valid;
  wire r2_valid;
  wire r3_valid;
  wire r4_valid;
  wire [`DP_LANES*LANE_SOP_W-1:0] lane_group_sum;
  wire [`DP_LANES*(`DP_Q_EXP_W+2)-1:0] lane_max_candidates;
  wire [`DP_LANES-1:0] lane_max_active;
  wire [`DP_LANES-1:0] lane_group_valid;
  wire [`DP_LANES-1:0] lane_group_all_negative;
  wire [`DP_LANES*`DP_SPECIAL_W-1:0] lane_group_special;
  wire signed [`DP_Q_EXP_W+1:0] group_max;
  wire max_active;
  assign q_request = in_valid & (in_datatype >= `DP_DT_MX8_E4M3) &
                     (in_datatype <= `DP_DT_MX6_E2M3);
  genvar lane_index;
  generate
    for (lane_index = 0; lane_index < `DP_LANES; lane_index = lane_index + 1) begin : g_lane
      wire [`DP_Q_EXP_W:0] candidate;
      wire [`DP_Q_EXP_W:0] unused_anchor;
      dp_lane_q #(.LOCAL_W(LOCAL_W)) u_lane (
        .clock(clock),
        .rst_n(rst_n),
        .in_valid(q_request),
        .in_datatype(in_datatype),
        .in_a(in_a[lane_index*`DP_LANE_W+:`DP_LANE_W]),
        .in_b(in_b[lane_index*`DP_LANE_W+:`DP_LANE_W]),
        .out_candidate(candidate),
        .out_candidate_active(lane_max_active[lane_index]),
        .in_group_max(group_max[`DP_Q_EXP_W:0]),
        .out_valid(lane_group_valid[lane_index]),
        .out_sop(lane_group_sum[lane_index*LANE_SOP_W+:LANE_SOP_W]),
        .out_anchor(unused_anchor),
        .out_special(lane_group_special[lane_index*`DP_SPECIAL_W+:`DP_SPECIAL_W]),
        .out_all_negative(lane_group_all_negative[lane_index])
      );
      assign lane_max_candidates[lane_index*(`DP_Q_EXP_W+2)+:`DP_Q_EXP_W+2] = {1'b0, candidate};
    end
  endgenerate
  dp_max_tree #(.N(`DP_LANES), .W(`DP_Q_EXP_W+2)) u_group_exponent_max (
    .in_values(lane_max_candidates),
    .in_active(lane_max_active),
    .out_max(group_max),
    .out_active(max_active)
  );
  // E8M0 scale has unity significand. Only signed exponent and NaN travel.
  wire signed [`DP_EXP_W-1:0] scale_a_exponent_d;
  wire signed [`DP_EXP_W-1:0] scale_b_exponent_d;
  wire signed [`DP_EXP_W-1:0] r1_scale_a_exponent;
  wire signed [`DP_EXP_W-1:0] r1_scale_b_exponent;
  wire r1_scale_nan;
  assign scale_a_exponent_d = in_scale_a - `DP_SCALE_BIAS;
  assign scale_b_exponent_d = in_scale_b - `DP_SCALE_BIAS;
  // S1 scale decode registers align with the lane's first boundary.
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(q_request), .out_q(r1_valid));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_scale_a_exponent (.clock(clock), .in_en(rst_n & q_request), .in_d(scale_a_exponent_d), .out_q(r1_scale_a_exponent));
  dp_lib_DFFE #(.WIDTH(`DP_EXP_W))
  ff_s0_s1_scale_b_exponent (.clock(clock), .in_en(rst_n & q_request), .in_d(scale_b_exponent_d), .out_q(r1_scale_b_exponent));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s0_s1_scale_nan (.clock(clock), .in_en(rst_n & q_request), .in_d((&in_scale_a) | (&in_scale_b)), .out_q(r1_scale_nan));
  // verilog_format: on
  // S2 signed scale sum and U6 common group MAX.
  wire signed [`DP_PRODUCT_EXP_W-1:0] scale_exponent_sum_d;
  wire signed [`DP_PRODUCT_EXP_W-1:0] r2_scale_exponent;
  wire [`DP_Q_EXP_W:0] r2_group_max;
  wire r2_scale_nan;
  assign scale_exponent_sum_d = {r1_scale_a_exponent[`DP_EXP_W-1], r1_scale_a_exponent} +
                                {r1_scale_b_exponent[`DP_EXP_W-1], r1_scale_b_exponent};
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  dp_lib_DFFE #(.WIDTH(`DP_PRODUCT_EXP_W))
  ff_s1_s2_scale_exponent (.clock(clock), .in_en(rst_n & r1_valid), .in_d(scale_exponent_sum_d), .out_q(r2_scale_exponent));
  dp_lib_DFFE #(.WIDTH(`DP_Q_EXP_W+1))
  ff_s1_s2_group_max (.clock(clock), .in_en(rst_n & r1_valid), .in_d(group_max[`DP_Q_EXP_W:0]), .out_q(r2_group_max));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_scale_nan (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_scale_nan), .out_q(r2_scale_nan));
  // verilog_format: on
  // S3 A_raw prepares the unchanged U31 token coordinate before S5 LZD.
  wire signed [ANCHOR_W-1:0] raw_anchor_d;
  wire signed [ANCHOR_W-1:0] r3_raw_anchor;
  wire signed [ANCHOR_W-1:0] r4_raw_anchor;
  wire r3_scale_nan;
  wire r4_scale_nan;
  assign raw_anchor_d = $signed({{(ANCHOR_W-`DP_Q_EXP_W-1){1'b0}}, r2_group_max}) +
      $signed({{(ANCHOR_W-`DP_PRODUCT_EXP_W){r2_scale_exponent[`DP_PRODUCT_EXP_W-1]}}, r2_scale_exponent}) +
      $signed(Q_ANCHOR_OFFSET[ANCHOR_W-1:0]);
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s2_s3_raw_anchor (.clock(clock), .in_en(rst_n & r2_valid), .in_d(raw_anchor_d), .out_q(r3_raw_anchor));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_scale_nan (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_scale_nan), .out_q(r3_scale_nan));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(r4_valid));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s3_s4_raw_anchor (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_raw_anchor), .out_q(r4_raw_anchor));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s3_s4_scale_nan (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_scale_nan), .out_q(r4_scale_nan));
  // verilog_format: on
  // S5 two-lane reduction, sign separation and common token representation.
  wire signed [GROUP_W-1:0] group_sum;
  wire [GROUP_W-1:0] absolute_sum;
  wire [MAG_W-1:0] magnitude_d;
  wire negative_d;
  wire [`DP_SPECIAL_W-1:0] merged_special;
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [$clog2(MAG_W+1)-1:0] zero_count;
  wire magnitude_active;
  wire signed [ANCHOR_W-1:0] anchor_d;
  wire signed [ANCHOR_W-1:0] compare_exp_d;
  wire [ANCHOR_W-1:0] observed_zero_count;
  dp_sum_tree #(.N(`DP_LANES), .W(LANE_SOP_W)) u_group_sop_add (
    .in_values(lane_group_sum),
    .out_sum(group_sum)
  );
  assign absolute_sum = group_sum[GROUP_W-1] ? -group_sum : group_sum;
  assign magnitude_d = absolute_sum[MAG_W-1:0];
  assign negative_d = group_sum[GROUP_W-1] | ((group_sum == 0) & (&lane_group_all_negative));
  assign merged_special = merge_special(lane_group_special[0+:`DP_SPECIAL_W], lane_group_special[`DP_SPECIAL_W+:`DP_SPECIAL_W]);
  // NaN E8M0 uses a zero numerical scale placeholder in the shared contract.
  // Preserve the same Inf-times-zero classification even when final D is NaN.
  wire zero_scale_infinity;
  assign zero_scale_infinity = r4_scale_nan &
      (merged_special[`DP_SP_POS_INF] | merged_special[`DP_SP_NEG_INF]);
  assign special_d[`DP_SP_NAN] = merged_special[`DP_SP_NAN] | r4_scale_nan;
  assign special_d[`DP_SP_INVALID] = merged_special[`DP_SP_INVALID] | zero_scale_infinity;
  assign special_d[`DP_SP_POS_INF] = merged_special[`DP_SP_POS_INF] & ~zero_scale_infinity;
  assign special_d[`DP_SP_NEG_INF] = merged_special[`DP_SP_NEG_INF] & ~zero_scale_infinity;
  dp_lzd #(.W(MAG_W)) u_group_leading_detect (
    .in_magnitude(magnitude_d),
    .out_count(zero_count),
    .out_active(magnitude_active)
  );
  assign anchor_d = (magnitude_active & (special_d == 0)) ? r4_raw_anchor : 0;
  assign compare_exp_d = (magnitude_active & (special_d == 0)) ?
      anchor_d - $signed({{(ANCHOR_W-$clog2(MAG_W+1)){1'b0}}, zero_count}) : 0;
  assign observed_zero_count = out_anchor - out_compare_exp;
  assign out_z = observed_zero_count[$clog2(MAG_W+1)-1:0];
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_valid (.clock(clock), .rst_n(rst_n), .in_d(r4_valid), .out_q(out_valid));
  dp_lib_DFFE #(.WIDTH(MAG_W))
  ff_s4_s5_magnitude (.clock(clock), .in_en(rst_n & r4_valid), .in_d(magnitude_d), .out_q(out_magnitude));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s4_s5_negative (.clock(clock), .in_en(rst_n & r4_valid), .in_d(negative_d), .out_q(out_negative));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_anchor (.clock(clock), .in_en(rst_n & r4_valid), .in_d(anchor_d), .out_q(out_anchor));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_compare_exp (.clock(clock), .in_en(rst_n & r4_valid), .in_d(compare_exp_d), .out_q(out_compare_exp));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s4_s5_special (.clock(clock), .in_en(rst_n & r4_valid), .in_d(special_d), .out_q(out_special));
  // verilog_format: on
endmodule
