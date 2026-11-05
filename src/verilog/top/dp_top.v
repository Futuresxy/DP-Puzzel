`include "dp_defs.vh"
// DP v1.4 independent hand-written RTL: T8H16Q32E64 at K_FP16=`DP_DEFAULT_K.
// Atomic A/B/C input, per-request type, II=1, L=8, no output backpressure.
// At edge n input is accepted into S1; S8 updates at n+7, observed before n+8.
// Synchronous active-high reset cancels all valid tokens. Datapath holds in bubbles.
// LOCAL_W sets S3 amplitude and the downstream leaf/lane/group widths.
// GLOBAL_W sets S6 signed alignment and the floating F=GLOBAL_W-2.
// K=K_FP16, N=K/4+1 including C, L=ceil(log2(N)). S7 TC output
// is S1I(1+L)F(GLOBAL_W-2) for all floats, or S1I(32+L)F(GLOBAL_W-33)
// for INT8+INT32. S8 output is encoded FP32 (S1/E8/F23) or TC S1I31F0.
module dp_top #(
  parameter integer K_FP16   = `DP_DEFAULT_K,
  parameter integer LOCAL_W  = `DP_DEFAULT_LOCAL_W,
  parameter integer GLOBAL_W = `DP_DEFAULT_GLOBAL_W,
  parameter integer GROUPS   = K_FP16 /`DP_GROUP_H
) (
  // verilog_format: off  // Keep ports sharing one declaration on the same line.
  input wire clock,reset,
  input wire in_a_valid,in_b_valid,in_c_valid,
  output wire out_a_ready,out_b_ready,out_c_ready,
  input wire [K_FP16*`DP_HALF_W-1:0] in_a,in_b,
  input wire [`DP_TYPE_W-1:0] in_a_datatype,in_b_datatype,
  input wire [GROUPS*`DP_SCALE_W-1:0] in_scale_a,in_scale_b,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_a_datatype,in_scale_b_datatype,
  input wire [GROUPS*4-1:0] in_hif4_e1_a,in_hif4_e1_b,
  input wire [GROUPS*2-1:0] in_hif4_e2_a,in_hif4_e2_b,
  input wire [`DP_FP32_W-1:0] in_c,
  input wire in_c_datatype,in_last,
  output wire out_valid,
  output reg [`DP_FP32_W-1:0] out_d,
  output wire out_d_datatype,out_last
  // verilog_format: on
);
  genvar g;
  integer i;

  `include "dp_functions.vh"
  localparam integer GROUP_W = LOCAL_W + 1 + $clog2(
    `DP_Q_LANES
  ) + $clog2(
    `DP_LANES
  ), GROUP_MAG_W = GROUP_W - 1, GLOBAL_MAG_W = GLOBAL_W - 1, N = GROUPS + 1,
    SUM_W = GLOBAL_W + $clog2(
    N
  ), ANCHOR_W = anchor_width(
    GLOBAL_MAG_W
  ), Z_W = $clog2(
    GLOBAL_MAG_W + 1
  ), INT_GROUP_F = GROUP_W - 1 - `DP_INT_PRODUCT_W - $clog2(
    `DP_Q_LANES
  ), INT_GLOBAL_F = GLOBAL_MAG_W - `DP_FP32_W;
  wire tuple_legal = (in_a_datatype <= `DP_DT_INT8) && (in_a_datatype == in_b_datatype) &&
    (in_c_datatype == (in_a_datatype == `DP_DT_INT8)) && (in_scale_a_datatype == scale_type(
    in_a_datatype
  )) && (in_scale_b_datatype == scale_type(
    in_a_datatype
  ));
  wire req_fire = !reset && in_a_valid && in_b_valid && in_c_valid && tuple_legal;
  assign out_a_ready = req_fire;
  assign out_b_ready = req_fire;
  assign out_c_ready = req_fire;
  reg [`DP_BASE_LATENCY-1:0] valid_q, last_q, c_type_q;
  reg [`DP_FP32_W-1:0] c_raw_q[0:3];
  assign out_valid = valid_q[`DP_BASE_LATENCY-1];
  assign out_last = last_q[`DP_BASE_LATENCY-1] && out_valid;
  assign out_d_datatype = c_type_q[`DP_BASE_LATENCY-1];
  wire [N*GLOBAL_MAG_W-1:0] source_magnitude;
  wire [N*ANCHOR_W-1:0] source_anchor;
  wire [N*Z_W-1:0] source_z;
  wire [N-1:0] source_negative;
  wire [N*`DP_SPECIAL_W-1:0] source_special;
  generate
    for (g = 0; g < GROUPS; g = g + 1) begin : g_group
      wire [GROUP_MAG_W-1:0] magnitude;
      wire signed [ANCHOR_W-1:0] anchor;
      wire [$clog2(GROUP_MAG_W+1)-1:0] leading;
      wire sign_value, valid;
      wire [`DP_SPECIAL_W-1:0] special_value;
      dp_group #(
        .LOCAL_W (LOCAL_W),
        .ANCHOR_W(ANCHOR_W)
      ) group_unit (
        .clock(clock),
        .reset(reset),
        .in_valid(req_fire),
        .in_datatype(in_a_datatype),
        .in_a(in_a[g*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
        .in_b(in_b[g*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
        .in_scale_a(in_scale_a[g*`DP_SCALE_W+:`DP_SCALE_W]),
        .in_scale_b(in_scale_b[g*`DP_SCALE_W+:`DP_SCALE_W]),
        .in_scale_datatype(in_scale_a_datatype),
        .in_e1_a(in_hif4_e1_a[g*4+:4]),
        .in_e1_b(in_hif4_e1_b[g*4+:4]),
        .in_e2_a(in_hif4_e2_a[g*2+:2]),
        .in_e2_b(in_hif4_e2_b[g*2+:2]),
        .out_valid(valid),
        .out_negative(sign_value),
        .out_magnitude(magnitude),
        .out_anchor(anchor),
        .out_z(leading),
        .out_special(special_value)
      );
      assign source_magnitude[g*GLOBAL_MAG_W+:GLOBAL_MAG_W] = c_type_q[4] ?
        (({{(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}, magnitude} >> INT_GROUP_F) << INT_GLOBAL_F) :
        {magnitude, {(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}};
      assign source_negative[g] = sign_value;
      assign source_anchor[g*ANCHOR_W+:ANCHOR_W] = anchor;
      assign source_z[g*Z_W+:Z_W] = {{(Z_W - $clog2(GROUP_MAG_W + 1)) {1'b0}}, leading};
      assign source_special[g*`DP_SPECIAL_W+:`DP_SPECIAL_W] = special_value;
    end
  endgenerate
  wire c_negative_d;
  wire [`DP_FP32_W-1:0] c_magnitude_d;
  wire signed [ANCHOR_W-1:0] c_anchor_d;
  wire [$clog2(`DP_FP32_W+1)-1:0] c_z_d;
  wire [`DP_SPECIAL_W-1:0] c_special_d;
  reg [`DP_SPECIAL_W-1:0] c_special_q;
  reg c_negative_q;
  reg [`DP_FP32_W-1:0] c_magnitude_q;
  reg signed [ANCHOR_W-1:0] c_anchor_q;
  reg [$clog2(`DP_FP32_W+1)-1:0] c_z_q;
  dp_c_unpack #(
    .ANCHOR_W(ANCHOR_W)
  ) c_unpack (
    .in_data(c_raw_q[3]),
    .in_datatype(c_type_q[3]),
    .out_negative(c_negative_d),
    .out_magnitude(c_magnitude_d),
    .out_anchor(c_anchor_d),
    .out_z(c_z_d),
    .out_special(c_special_d)
  );
  assign source_magnitude[GROUPS*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {
    c_magnitude_q, {(GLOBAL_MAG_W - `DP_FP32_W) {1'b0}}
  };
  assign source_negative[GROUPS] = c_negative_q;
  assign source_anchor[GROUPS*ANCHOR_W+:ANCHOR_W] = c_anchor_q;
  assign source_z[GROUPS*Z_W+:Z_W] = (c_z_q);
  assign source_special[GROUPS*`DP_SPECIAL_W+:`DP_SPECIAL_W] = c_special_q;
  wire [N*GLOBAL_W-1:0] leaves_d;
  reg [N*GLOBAL_W-1:0] leaves_q;
  wire signed [ANCHOR_W-1:0] common_d;
  reg signed [ANCHOR_W-1:0] common_s6_q, common_s7_q;
  wire negative_zero_d;
  reg negative_zero_s6_q, negative_zero_s7_q;
  wire [`DP_SPECIAL_W-1:0] special_d;
  reg [`DP_SPECIAL_W-1:0] special_s6_q, special_s7_q;
  dp_global_align #(
    .N(N),
    .MAG_W(GLOBAL_MAG_W),
    .ANCHOR_W(ANCHOR_W)
  ) global_alignment (
    .in_integer(c_type_q[4]),
    .in_enable(valid_q[4]),
    .in_magnitude(source_magnitude),
    .in_anchor(source_anchor),
    .in_z(source_z),
    .in_negative(source_negative),
    .in_special(source_special),
    .out_leaves(leaves_d),
    .out_anchor(common_d),
    .out_negative_zero(negative_zero_d),
    .out_special(special_d)
  );
  wire signed [SUM_W-1:0] sum_d;
  reg signed  [SUM_W-1:0] sum_q;
  dp_sum_tree #(
    .N(N),
    .W(GLOBAL_W)
  ) final_sop_tree (
    .in_values(leaves_q),
    .out_sum  (sum_d)
  );
  wire [`DP_FP32_W-1:0] finite_result;
  // Isolate S8 floating arithmetic for integer requests.
  wire signed [SUM_W-1:0] float_sum = c_type_q[6] ? 0 : sum_q;
  dp_fp32_round #(
    .SUM_W(SUM_W),
    .ANCHOR_W(ANCHOR_W),
    .GLOBAL_MAG_W(GLOBAL_MAG_W)
  ) fp32_output (
    .in_sum(float_sum),
    .in_anchor(common_s7_q),
    .in_negative_zero(negative_zero_s7_q),
    .out_bits(finite_result)
  );
  always @(posedge clock) begin
    if (reset) begin
      valid_q  <= 0;
      last_q   <= 0;
      c_type_q <= 0;
    end else begin
      valid_q <= {valid_q[`DP_BASE_LATENCY-2:0], req_fire};
      last_q  <= {last_q[`DP_BASE_LATENCY-2:0], req_fire && in_last};
      if (req_fire) begin
        c_raw_q[0]  <= in_c;
        c_type_q[0] <= in_c_datatype;
      end
      for (i = 1; i < `DP_BASE_LATENCY; i = i + 1) if (valid_q[i-1]) c_type_q[i] <= c_type_q[i-1];
      for (i = 1; i < 4; i = i + 1) if (valid_q[i-1]) c_raw_q[i] <= c_raw_q[i-1];
      if (valid_q[3]) begin
        c_negative_q <= c_negative_d;
        c_magnitude_q <= c_magnitude_d;
        c_anchor_q <= c_anchor_d;
        c_z_q <= c_z_d;
        c_special_q <= c_special_d;
      end
      if (valid_q[4]) begin
        leaves_q <= leaves_d;
        common_s6_q <= common_d;
        negative_zero_s6_q <= negative_zero_d;
        special_s6_q <= special_d;
      end
      if (valid_q[5]) begin
        sum_q <= sum_d;
        common_s7_q <= common_s6_q;
        negative_zero_s7_q <= negative_zero_s6_q;
        special_s7_q <= special_s6_q;
      end
      if (valid_q[6]) begin
        if (c_type_q[6]) out_d <= sum_q[INT_GLOBAL_F+:`DP_FP32_W];
        else if (special_s7_q[`DP_SP_NAN] || special_s7_q[`DP_SP_INVALID]) out_d <= `DP_FP32_QNAN;
        else if (special_s7_q[`DP_SP_POS_INF] || special_s7_q[`DP_SP_NEG_INF])
          out_d <= `DP_FP32_INF | {special_s7_q[`DP_SP_NEG_INF], {(`DP_FP32_W - 1) {1'b0}}};
        else out_d <= finite_result;
      end
    end
  end
  // Elaboration constraints are validation only; no synthesized datapath/reset.
  // synthesis translate_off
  initial begin
    if (K_FP16 != 4 && K_FP16 != 8 && K_FP16 != 16) begin
      $display("FAIL: %s", "K_FP16 must be 4, 8 or 16");
      $finish;
    end
    if (GROUPS != K_FP16 / `DP_GROUP_H) begin
      $display("FAIL: %s", "GROUPS is derived");
      $finish;
    end
    if (LOCAL_W < `DP_MIN_LOCAL_W) begin
      $display("FAIL: %s", "LOCAL_W requires at least F25");
      $finish;
    end
    if (GLOBAL_MAG_W < GROUP_MAG_W || GLOBAL_MAG_W < `DP_FP32_W) begin
      $display("FAIL: %s", "global window is smaller than source");
      $finish;
    end
  end
  // synthesis translate_on
endmodule
