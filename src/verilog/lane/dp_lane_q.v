`include "dp_defs.vh"
// Q4 only; S1 decode/classify, S2 products/common group MAX, S3 RTZ, S4 tree.
// Four 4x4 unsigned multipliers; no E pair, HiF metadata or E mode selection.
// Fixed II=1, lane output S4, synchronous low reset for valid, enabled payload.
// S3 leaf S1I2F(LOCAL_W-2); S4 SOP S1I4F(LOCAL_W-2).
module dp_lane_q #(
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
  output wire [`DP_Q_EXP_W:0] out_candidate,
  output wire out_candidate_active,
  input wire [`DP_Q_EXP_W:0] in_group_max,
  output wire out_valid,
  output wire signed [LANE_SOP_W-1:0] out_sop,
  output wire [`DP_Q_EXP_W:0] out_anchor,
  output wire [`DP_SPECIAL_W-1:0] out_special,
  output wire out_all_negative
);
  // Natural product width and common exponent sum width.
  localparam integer PRODUCT_W = 2 * `DP_EIGHTH_W;
  localparam integer EXPONENT_W = `DP_Q_EXP_W + 1;
  localparam integer PRODUCT_PAD = LOCAL_W - 2 - 2 * `DP_SCALE_F;
  // Valid always advances; payload changes only on an accepted Q request.
  wire q_request;
  wire r1_valid;
  wire r2_valid;
  wire r3_valid;
  wire [`DP_Q_LANES*(EXPONENT_W+1)-1:0] product_max_values;
  wire [`DP_Q_LANES-1:0] r1_product_active;
  wire [`DP_Q_LANES-1:0] product_negative_d;
  wire [`DP_Q_LANES-1:0] nan_sources;
  wire [`DP_Q_LANES-1:0] invalid_sources;
  wire [`DP_Q_LANES-1:0] positive_inf_sources;
  wire [`DP_Q_LANES-1:0] negative_inf_sources;
  wire [`DP_Q_LANES*LEAF_W-1:0] r3_aligned_leaves;
  wire signed [EXPONENT_W:0] exponent_max;
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] r1_special;
  wire [`DP_SPECIAL_W-1:0] r2_special;
  wire [`DP_SPECIAL_W-1:0] r3_special;
  wire r1_all_negative;
  wire r2_all_negative;
  wire r3_all_negative;
  wire [EXPONENT_W-1:0] r2_anchor;
  wire [EXPONENT_W-1:0] r3_anchor;
  wire signed [LANE_SOP_W-1:0] lane_sum_d;
  assign q_request = in_valid & (in_datatype >= `DP_DT_MX8_E4M3) &
                     (in_datatype <= `DP_DT_MX6_E2M3);
  genvar element_index;
  // S1 data and control share one pipeline boundary.
  wire [`DP_EIGHTH_W-1:0] r1_a_magnitude[0:`DP_Q_LANES-1];
  wire [`DP_EIGHTH_W-1:0] r1_b_magnitude[0:`DP_Q_LANES-1];
  wire [`DP_Q_EXP_W-1:0] r1_a_exponent[0:`DP_Q_LANES-1];
  wire [`DP_Q_EXP_W-1:0] r1_b_exponent[0:`DP_Q_LANES-1];
  wire r1_negative[0:`DP_Q_LANES-1];
  generate
    for (element_index = 0; element_index < `DP_Q_LANES; element_index = element_index + 1) begin : g_s1_element
      // S1 decoded operands; classification is paired before registration.
      wire [`DP_EIGHTH_W-1:0] a_magnitude_d;
      wire [`DP_EIGHTH_W-1:0] b_magnitude_d;
      wire [`DP_Q_EXP_W-1:0] a_exponent_d;
      wire [`DP_Q_EXP_W-1:0] b_exponent_d;
      wire a_negative;
      wire b_negative;
      wire [`DP_NUM_CLASS_W-1:0] a_class;
      wire [`DP_NUM_CLASS_W-1:0] b_class;
      wire a_signaling;
      wire b_signaling;
      wire pair_nan;
      wire pair_inf;
      wire pair_zero;
      wire pair_infinity;
      dp_operand_unpack_q #(.INDEX(element_index)) u_operand_a (
        .in_data(in_a),
        .in_datatype(in_datatype),
        .out_magnitude(a_magnitude_d),
        .out_exponent(a_exponent_d),
        .out_negative(a_negative),
        .out_class(a_class),
        .out_signaling(a_signaling)
      );
      dp_operand_unpack_q #(.INDEX(element_index)) u_operand_b (
        .in_data(in_b),
        .in_datatype(in_datatype),
        .out_magnitude(b_magnitude_d),
        .out_exponent(b_exponent_d),
        .out_negative(b_negative),
        .out_class(b_class),
        .out_signaling(b_signaling)
      );
      assign pair_nan = (a_class == `DP_CLASS_NAN) | (b_class == `DP_CLASS_NAN);
      assign pair_inf = (a_class == `DP_CLASS_INF) | (b_class == `DP_CLASS_INF);
      assign pair_zero = (a_class == `DP_CLASS_ZERO) | (b_class == `DP_CLASS_ZERO);
      assign pair_infinity = pair_inf & ~pair_zero & ~pair_nan;
      assign product_negative_d[element_index] = a_negative ^ b_negative;
      assign nan_sources[element_index] = pair_nan;
      assign invalid_sources[element_index] = a_signaling | b_signaling | (pair_inf & pair_zero);
      assign positive_inf_sources[element_index] = pair_infinity & ~product_negative_d[element_index];
      assign negative_inf_sources[element_index] = pair_infinity & product_negative_d[element_index];
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_EIGHTH_W))
      ff_s0_s1_a_magnitude (.clock(clock), .in_en(rst_n & q_request), .in_d(a_magnitude_d), .out_q(r1_a_magnitude[element_index]));
      dp_lib_DFFE #(.WIDTH(`DP_EIGHTH_W))
      ff_s0_s1_b_magnitude (.clock(clock), .in_en(rst_n & q_request), .in_d(b_magnitude_d), .out_q(r1_b_magnitude[element_index]));
      dp_lib_DFFE #(.WIDTH(`DP_Q_EXP_W))
      ff_s0_s1_a_exponent (.clock(clock), .in_en(rst_n & q_request), .in_d(a_exponent_d), .out_q(r1_a_exponent[element_index]));
      dp_lib_DFFE #(.WIDTH(`DP_Q_EXP_W))
      ff_s0_s1_b_exponent (.clock(clock), .in_en(rst_n & q_request), .in_d(b_exponent_d), .out_q(r1_b_exponent[element_index]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s0_s1_negative (.clock(clock), .in_en(rst_n & q_request), .in_d(product_negative_d[element_index]), .out_q(r1_negative[element_index]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s0_s1_active (.clock(clock), .in_en(rst_n & q_request), .in_d((a_class == `DP_CLASS_FINITE) & (b_class == `DP_CLASS_FINITE)), .out_q(r1_product_active[element_index]));
      // verilog_format: on
    end
  endgenerate
  assign special_d[`DP_SP_NAN] = |nan_sources;
  assign special_d[`DP_SP_INVALID] = (|invalid_sources) | ((|positive_inf_sources) & (|negative_inf_sources));
  assign special_d[`DP_SP_POS_INF] = |positive_inf_sources;
  assign special_d[`DP_SP_NEG_INF] = |negative_inf_sources;
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(q_request), .out_q(r1_valid));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s0_s1_special (.clock(clock), .in_en(rst_n & q_request), .in_d(special_d), .out_q(r1_special));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s0_s1_all_negative (.clock(clock), .in_en(rst_n & q_request), .in_d(&product_negative_d), .out_q(r1_all_negative));
  // verilog_format: on
  // S2 data and control share one pipeline boundary.
  wire [PRODUCT_W-1:0] r2_product[0:`DP_Q_LANES-1];
  wire [EXPONENT_W-1:0] r2_exponent[0:`DP_Q_LANES-1];
  wire r2_negative[0:`DP_Q_LANES-1];
  wire r2_active[0:`DP_Q_LANES-1];
  generate
    for (element_index = 0; element_index < `DP_Q_LANES; element_index = element_index + 1) begin : g_s2_element
      // S2 multiplier and exponent addition execute in parallel with group MAX.
      wire [PRODUCT_W-1:0] product_d;
      wire [EXPONENT_W-1:0] exponent_d;
      dp_mul_unsigned #(.A_W(`DP_EIGHTH_W), .B_W(`DP_EIGHTH_W)) u_product (
        .in_a(r1_a_magnitude[element_index]),
        .in_b(r1_b_magnitude[element_index]),
        .out_product(product_d)
      );
      assign exponent_d = {1'b0, r1_a_exponent[element_index]} + {1'b0, r1_b_exponent[element_index]};
      assign product_max_values[element_index*(EXPONENT_W+1)+:EXPONENT_W+1] = {1'b0, exponent_d};
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(PRODUCT_W))
      ff_s1_s2_product (.clock(clock), .in_en(rst_n & r1_valid), .in_d(product_d), .out_q(r2_product[element_index]));
      dp_lib_DFFE #(.WIDTH(EXPONENT_W))
      ff_s1_s2_exponent (.clock(clock), .in_en(rst_n & r1_valid), .in_d(exponent_d), .out_q(r2_exponent[element_index]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s1_s2_negative (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_negative[element_index]), .out_q(r2_negative[element_index]));
      dp_lib_DFFE #(.WIDTH(1))
      ff_s1_s2_active (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_product_active[element_index]), .out_q(r2_active[element_index]));
      // verilog_format: on
    end
  endgenerate
  dp_max_tree #(.N(`DP_Q_LANES), .W(EXPONENT_W+1)) u_lane_exponent_max (
    .in_values(product_max_values),
    .in_active(r1_product_active),
    .out_max(exponent_max),
    .out_active(out_candidate_active)
  );
  assign out_candidate = exponent_max[EXPONENT_W-1:0];
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s1_s2_special (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_special), .out_q(r2_special));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s1_s2_all_negative (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_all_negative), .out_q(r2_all_negative));
  dp_lib_DFFE #(.WIDTH(EXPONENT_W))
  ff_s1_s2_anchor (.clock(clock), .in_en(rst_n & r1_valid), .in_d(in_group_max), .out_q(r2_anchor));
  // verilog_format: on
  // S3 data and control share one pipeline boundary.
  generate
    for (element_index = 0; element_index < `DP_Q_LANES; element_index = element_index + 1) begin : g_s3_element
      // S3 magnitude RTZ then restore sign; zero/special leaves cannot set MAX.
      wire [LOCAL_W-1:0] shift_input;
      wire [EXPONENT_W-1:0] shift_distance;
      wire [LOCAL_W-1:0] shifted_magnitude;
      wire signed [LEAF_W-1:0] leaf_d;
      assign shift_input = (r2_valid & r2_active[element_index]) ? {r2_product[element_index], {PRODUCT_PAD{1'b0}}} : 0;
      assign shift_distance = r2_active[element_index] ? r2_anchor - r2_exponent[element_index] : 0;
      dp_rtz_shift #(.W(LOCAL_W), .SHIFT_W(EXPONENT_W)) u_local_align_shift (
        .in_magnitude(shift_input),
        .in_shift(shift_distance),
        .out_magnitude(shifted_magnitude)
      );
      assign leaf_d = r2_negative[element_index] ? -$signed({1'b0, shifted_magnitude}) : $signed({1'b0, shifted_magnitude});
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(LEAF_W))
      ff_s2_s3_leaf (.clock(clock), .in_en(rst_n & r2_valid), .in_d(leaf_d), .out_q(r3_aligned_leaves[element_index*LEAF_W+:LEAF_W]));
      // verilog_format: on
    end
  endgenerate
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s2_s3_special (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_special), .out_q(r3_special));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s2_s3_all_negative (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_all_negative), .out_q(r3_all_negative));
  dp_lib_DFFE #(.WIDTH(EXPONENT_W))
  ff_s2_s3_anchor (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_anchor), .out_q(r3_anchor));
  // verilog_format: on
  // S4 balanced four-input tree, retaining both carry growth bits.
  dp_sum_tree #(.N(`DP_Q_LANES), .W(LEAF_W)) u_lane_sop_tree (
    .in_values(r3_aligned_leaves),
    .out_sum(lane_sum_d)
  );
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(out_valid));
  dp_lib_DFFE #(.WIDTH(LANE_SOP_W))
  ff_s3_s4_sop (.clock(clock), .in_en(rst_n & r3_valid), .in_d(lane_sum_d), .out_q(out_sop));
  dp_lib_DFFE #(.WIDTH(EXPONENT_W))
  ff_s3_s4_anchor (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_anchor), .out_q(out_anchor));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s3_s4_special (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_special), .out_q(out_special));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s3_s4_all_negative (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_all_negative), .out_q(out_all_negative));
  // verilog_format: on
endmodule
