`include "dp_defs.vh"
// E16 group: two E8 lanes; S4 sum/abs, S5 unsigned scale/LZD/token.
// L5 from atomic input, II=1. No element-exponent MAX/delta/right alignment.
// Synchronous high reset cancels valid. Data registers hold in bubbles.
// TC -> independent sign+magnitude at S4. I excludes sign; M=LOCAL_W+3.
// Precision    | S4 S | I  | F | Scale A S | I  | F | Scale B S | I | F | Product S | I  | F
// ------------ | ---- | -- | - | --------- | -- | - | --------- | - | - | --------- | -- | --
// NVFP4/HiF4   | 1    | 10 | 4 | 0         | 10 | 4 | 0         | 2 | 6 | 0         | 12 | 10
// MXFP4        | 1    | 10 | 4 | bypass    | 10 | 4 | unused    | - | - | bypass    | 10 | 4
// S5 output (SM); sign is separate through global alignment.
// Precision    | S | I  | F
// ------------ | - | -- | ----
// MXFP4        | 1 | 10 | M-10
// NVFP4/HiF4   | 1 | 12 | M-12
module dp_group_e #(
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  parameter integer MAG_W = LOCAL_W + 3,
  parameter integer ANCHOR_W = anchor_width(MAG_W)
) (
  // verilog_format: off
  input wire clock,reset,in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_a,in_b,
  input wire [`DP_SCALE_W-1:0] in_scale_a,in_scale_b,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_datatype,
  input wire [3:0] in_e1_a,in_e1_b,
  input wire [1:0] in_e2_a,in_e2_b,
  output reg out_valid,out_negative,
  output reg [MAG_W-1:0] out_magnitude,
  output reg signed [ANCHOR_W-1:0] out_anchor,
  output reg [$clog2(MAG_W+1)-1:0] out_z,
  output reg [`DP_SPECIAL_W-1:0] out_special
  // verilog_format: on
);
  `include "dp_functions.vh"
  localparam integer PAIR_W = 2 * `DP_MUL_LO + 2, LANE_W = PAIR_W + $clog2(
    `DP_E_LANES / 2
  ), FUSED_W = LANE_W + `DP_E_GUARD, GROUP_W = FUSED_W + $clog2(
    `DP_LANES
  ), COMPACT_W = GROUP_W - 1, COEFF_W = 2 * `DP_SCALE_M, PRODUCT_W = COMPACT_W + COEFF_W;
  reg [3:0] valid_q;
  reg [`DP_TYPE_W-1:0] type_s1_q, type_s2_q, type_s3_q, type_s4_q;
  wire [`DP_LANES*FUSED_W-1:0] lane_sops;
  wire [`DP_LANES-1:0] lane_negative, lane_valid;
  genvar j;
  generate
    for (j = 0; j < `DP_LANES; j = j + 1) begin : g_lane
      dp_lane_e lane (
        .clock(clock),
        .reset(reset),
        .in_valid(in_valid),
        .in_datatype(in_datatype),
        .in_a(in_a[j*`DP_LANE_W+:`DP_LANE_W]),
        .in_b(in_b[j*`DP_LANE_W+:`DP_LANE_W]),
        .in_e1_a(in_e1_a[j*2+:2]),
        .in_e1_b(in_e1_b[j*2+:2]),
        .in_e2_a(in_e2_a[j]),
        .in_e2_b(in_e2_b[j]),
        .out_valid(lane_valid[j]),
        .out_all_negative(lane_negative[j]),
        .out_sop(lane_sops[j*FUSED_W+:FUSED_W])
      );
    end
  endgenerate
  wire [COEFF_W-1:0] coefficient_d;
  wire [`DP_SCALE_M-1:0] sa_d, sb_d;
  wire [`DP_EXP_W-1:0] ea_d, eb_d;
  wire na_d, nb_d;
  reg [`DP_SCALE_M-1:0] sa_s1_q, sb_s1_q;
  reg [`DP_EXP_W-1:0] ea_s1_q, eb_s1_q;
  reg nan_s1_q, nan_s2_q, nan_s3_q, nan_s4_q;
  reg [COEFF_W-1:0] coeff_s2_q, coeff_s3_q, coeff_s4_q;
  reg [`DP_PRODUCT_EXP_W-1:0] scale_exp_s2_q;
  reg signed [ANCHOR_W-1:0] anchor_s3_q, anchor_s4_q;
  dp_scale_unpack scale_unpack_a (
    .in_data(in_scale_a),
    .in_datatype(in_scale_datatype),
    .out_magnitude(sa_d),
    .out_exponent(ea_d),
    .out_nan(na_d)
  );
  dp_scale_unpack scale_unpack_b (
    .in_data(in_scale_b),
    .in_datatype(in_scale_datatype),
    .out_magnitude(sb_d),
    .out_exponent(eb_d),
    .out_nan(nb_d)
  );
  dp_mul_unsigned #(
    .A_W(`DP_SCALE_M),
    .B_W(`DP_SCALE_M)
  ) scale_pair_mul (
    .in_a(sa_s1_q),
    .in_b(sb_s1_q),
    .out_product(coefficient_d)
  );
  wire signed [GROUP_W-1:0] group_sum;
  dp_sum_tree #(
    .N(`DP_LANES),
    .W(FUSED_W)
  ) group_sop_add (
    .in_values(lane_sops),
    .out_sum  (group_sum)
  );
  wire [GROUP_W-1:0] absolute_sop = group_sum[GROUP_W-1] ? -group_sum : group_sum;
  reg [COMPACT_W-1:0] magnitude_s4_q;
  reg negative_s4_q;
  // Both MX and NV share F4 before scale. HiF4 e2 is consumed inside each lane.
  wire inject_scale = valid_q[3] && type_s4_q != `DP_DT_MXFP4;
  wire [COMPACT_W-1:0] scale_magnitude = inject_scale ? magnitude_s4_q : 0;
  wire [COEFF_W-1:0] scale_coefficient = inject_scale ? coeff_s4_q : 0;
  wire [PRODUCT_W-1:0] scale_product;
  dp_scale_multiply group_scale_mul (
    .in_magnitude(scale_magnitude),
    .in_coefficient(scale_coefficient),
    .out_product(scale_product)
  );
  wire [MAG_W-1:0] magnitude_d = inject_scale ?
    {scale_product, {(MAG_W - PRODUCT_W) {1'b0}}} : {magnitude_s4_q, {(MAG_W - COMPACT_W) {1'b0}}};
  wire [$clog2(MAG_W+1)-1:0] leading_d;
  wire magnitude_active;
  dp_lzd #(
    .W(MAG_W)
  ) group_leading_detect (
    .in_magnitude(magnitude_d),
    .out_count(leading_d),
    .out_active(magnitude_active)
  );
  integer anchor_work;
  always @* begin
    // alpha - F + M-1; F=M-10 (MX), M-12 (NV/HiF).
    anchor_work = {{(32 - `DP_PRODUCT_EXP_W) {1'b0}}, scale_exp_s2_q} - 2 * `DP_SCALE_BIAS;
    anchor_work = anchor_work + (type_s2_q == `DP_DT_MXFP4 ? 9 : 11);
  end
  always @(posedge clock) begin
    if (reset) begin
      valid_q   <= 0;
      out_valid <= 0;
    end else begin
      valid_q   <= {valid_q[2:0], in_valid};
      out_valid <= valid_q[3];
      if (in_valid) begin
        type_s1_q <= in_datatype;
        sa_s1_q   <= sa_d;
        sb_s1_q   <= sb_d;
        ea_s1_q   <= ea_d;
        eb_s1_q   <= eb_d;
        nan_s1_q  <= na_d | nb_d;
      end
      if (valid_q[0]) begin
        type_s2_q <= type_s1_q;
        coeff_s2_q <= coefficient_d;
        scale_exp_s2_q <= {1'b0, ea_s1_q} + {1'b0, eb_s1_q};
        nan_s2_q <= nan_s1_q;
      end
      if (valid_q[1]) begin
        type_s3_q <= type_s2_q;
        coeff_s3_q <= coeff_s2_q;
        nan_s3_q <= nan_s2_q;
        anchor_s3_q <= anchor_work[ANCHOR_W-1:0];
      end
      if (valid_q[2]) begin
        type_s4_q <= type_s3_q;
        coeff_s4_q <= coeff_s3_q;
        nan_s4_q <= nan_s3_q;
        anchor_s4_q <= anchor_s3_q;
        magnitude_s4_q <= absolute_sop[COMPACT_W-1:0];
        negative_s4_q <= group_sum[GROUP_W-1] || (group_sum == 0 && (&lane_negative));
      end
      if (valid_q[3]) begin
        out_magnitude <= magnitude_d;
        out_negative <= negative_s4_q;
        out_special <= {nan_s4_q, 3'b000};
        out_anchor <= magnitude_active && !nan_s4_q ? anchor_s4_q : 0;
        out_z <= !nan_s4_q ? leading_d : 0;
      end
    end
  end
endmodule
