`include "dp_defs.vh"
// T2H4Q8E16: two synchronized lanes, S2 common MAX, S5 scale/abs/LZD.
// Owns S1 scale decode and S2 scale-pair arithmetic; transport stops at S4.
// Output is unnormalized sign/magnitude, A_raw=alpha-F+(M-1), plus z.
module dp_group #(
  parameter integer LOCAL_W=`DP_DEFAULT_LOCAL_W,
  parameter integer LANE_SOP_W=LOCAL_W+1+$clog2(`DP_Q_LANES),
  parameter integer GROUP_W=LANE_SOP_W+$clog2(`DP_LANES),
  parameter integer MAG_W=GROUP_W-1,
  parameter integer ANCHOR_W=anchor_width(MAG_W)
)(
  input wire clock,reset,in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANES*`DP_LANE_W-1:0] in_a,in_b,
  input wire [`DP_SCALE_W-1:0] in_scale_a,in_scale_b,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_datatype,
  input wire [3:0] in_e1_a,in_e1_b, input wire [1:0] in_e2_a,in_e2_b,
  output reg out_valid,out_negative,
  output reg [MAG_W-1:0] out_magnitude,
  output reg signed [ANCHOR_W-1:0] out_anchor,
  output reg [$clog2(MAG_W+1)-1:0] out_z,
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar gen_i;
  integer i;

  `include "dp_functions.vh"
  localparam integer COEFF_W=2*`DP_SCALE_M, SCALE_PRODUCT_W=`DP_SCALE_SOP_W+COEFF_W+1,
    USEFUL_SCALE_W=SCALE_PRODUCT_W-1, STRUCTURAL_DROP=GROUP_W-`DP_SCALE_SOP_W,
    SCALE_LOW_PAD=GROUP_W-USEFUL_SCALE_W;
  reg [3:0] valid_q;
  reg [`DP_TYPE_W-1:0] type_q [0:3];
  wire [`DP_LANES*LANE_SOP_W-1:0] lane_sops;
  wire [`DP_LANES*(`DP_PRODUCT_EXP_W+1)-1:0] lane_candidates;
  wire [`DP_LANES-1:0] lane_active,lane_negative,lane_valid;
  wire [`DP_LANES*`DP_SPECIAL_W-1:0] lane_special;
  wire [`DP_PRODUCT_EXP_W-1:0] lane_anchor [0:`DP_LANES-1];
  wire signed [`DP_PRODUCT_EXP_W:0] group_max;
  wire max_active;
  generate
  for(gen_i=0;gen_i<`DP_LANES;gen_i=gen_i+1) begin: g_lane
    wire [`DP_PRODUCT_EXP_W-1:0] candidate;
    wire [`DP_SPECIAL_W-1:0] special_value;
    dp_lane #(.LOCAL_W(LOCAL_W)) lane(
      .clock(clock),.reset(reset),.in_valid(in_valid),.in_datatype(in_datatype),
      .in_a(in_a[gen_i*`DP_LANE_W+:`DP_LANE_W]),.in_b(in_b[gen_i*`DP_LANE_W+:`DP_LANE_W]),
      .in_e1_a(in_e1_a[gen_i*2+:2]),.in_e1_b(in_e1_b[gen_i*2+:2]),.in_e2_a(in_e2_a[gen_i]),.in_e2_b(in_e2_b[gen_i]),
      .out_candidate(candidate),.out_candidate_active(lane_active[gen_i]),.in_group_max(group_max[`DP_PRODUCT_EXP_W-1:0]),
      .out_valid(lane_valid[gen_i]),.out_sop(lane_sops[gen_i*LANE_SOP_W+:LANE_SOP_W]),
      .out_anchor(lane_anchor[gen_i]),.out_special(special_value),.out_all_negative(lane_negative[gen_i]));
    assign lane_candidates[gen_i*(`DP_PRODUCT_EXP_W+1)+:`DP_PRODUCT_EXP_W+1]={1'b0,candidate};
    assign lane_special[gen_i*`DP_SPECIAL_W+:`DP_SPECIAL_W]=special_value;
  end endgenerate
  dp_max_tree #(.N(`DP_LANES),.W(`DP_PRODUCT_EXP_W+1)) group_exponent_max(
    .in_values(lane_candidates),.in_active(lane_active),.out_max(group_max),.out_active(max_active));
  wire [`DP_SCALE_M-1:0] sa_d,sb_d;
  wire [`DP_EXP_W-1:0] ea_d,eb_d;
  wire na_d,nb_d;
  reg [`DP_SCALE_M-1:0] sa_q,sb_q;
  reg [`DP_EXP_W-1:0] ea_q,eb_q;
  reg nan_s1_q;
  wire [COEFF_W-1:0] coeff_d;
  reg [COEFF_W-1:0] coeff_q [1:3];
  reg [`DP_PRODUCT_EXP_W-1:0] scale_exp_q [1:3];
  reg scale_nan_q [1:3];
  dp_scale_unpack scale_unpack_a(.in_data(in_scale_a),.in_datatype(in_scale_datatype),.out_magnitude(sa_d),.out_exponent(ea_d),.out_nan(na_d));
  dp_scale_unpack scale_unpack_b(.in_data(in_scale_b),.in_datatype(in_scale_datatype),.out_magnitude(sb_d),.out_exponent(eb_d),.out_nan(nb_d));
  dp_mul_unsigned #(.A_W(`DP_SCALE_M),.B_W(`DP_SCALE_M)) scale_pair_mul(.in_a(sa_q),.in_b(sb_q),.out_product(coeff_d));
  wire signed [GROUP_W-1:0] group_sum;
  dp_sum_tree #(.N(`DP_LANES),.W(LANE_SOP_W)) group_sop_add(.in_values(lane_sops),.out_sum(group_sum));
  wire inject_scale=(type_q[3]==`DP_DT_NVFP4 || type_q[3]==`DP_DT_HIF4) && valid_q[3];
  wire signed [`DP_SCALE_SOP_W-1:0] compact_sop=inject_scale ? group_sum[STRUCTURAL_DROP+:`DP_SCALE_SOP_W] : 0;
  wire signed [COEFF_W:0] compact_coeff=inject_scale ? {1'b0,coeff_q[3]} : 0;
  wire signed [SCALE_PRODUCT_W-1:0] scale_product;
  dp_scale_multiply group_scale_mul(.in_sop(compact_sop),.in_coefficient(compact_coeff),.out_product(scale_product));
  wire signed [GROUP_W-1:0] selected_sop=inject_scale ? {scale_product[USEFUL_SCALE_W-1:0],{SCALE_LOW_PAD{1'b0}}} : group_sum;
  wire [GROUP_W-1:0] absolute_sop=selected_sop[GROUP_W-1] ? -selected_sop : selected_sop;
  wire [MAG_W-1:0] magnitude_d=absolute_sop[MAG_W-1:0];
  wire [$clog2(MAG_W+1)-1:0] z_d;
  wire magnitude_active;
  dp_lzd #(.W(MAG_W)) group_leading_detect(.in_magnitude(magnitude_d),.out_count(z_d),.out_active(magnitude_active));
  reg [`DP_SPECIAL_W-1:0] special_d,special_q,lane0,lane1;
  reg signed [ANCHOR_W-1:0] anchor_d;
  reg negative_d;
  integer anchor_work;
  assign out_special=special_q;
  always @* begin
    lane0=lane_special[0+:`DP_SPECIAL_W]; lane1=lane_special[`DP_SPECIAL_W+:`DP_SPECIAL_W];
    special_d=merge_special(lane0,lane1);
    special_d[`DP_SP_NAN]=special_d[`DP_SP_NAN] | scale_nan_q[3];
    if(coeff_q[3]==0 && (special_d[`DP_SP_POS_INF] || special_d[`DP_SP_NEG_INF])) begin
      special_d[`DP_SP_INVALID]=1; special_d[`DP_SP_POS_INF]=0; special_d[`DP_SP_NEG_INF]=0;
    end
    negative_d=selected_sop[GROUP_W-1] || (selected_sop==0 && (group_sum[GROUP_W-1] || (&lane_negative)));
    anchor_work=({{(32-`DP_PRODUCT_EXP_W){1'b0}},lane_anchor[0]}-2*element_bias(type_q[3])-group_fraction(type_q[3],LOCAL_W)+MAG_W-1);
    if(scale_type(type_q[3])!=`DP_SC_NONE)
      anchor_work=anchor_work+({{(32-`DP_PRODUCT_EXP_W){1'b0}},scale_exp_q[3]}-2*`DP_SCALE_BIAS);
    anchor_d=anchor_work[ANCHOR_W-1:0];
    if(!magnitude_active || special_d!=0 || type_q[3]==`DP_DT_INT8) anchor_d=0;
  end
  always @(posedge clock) begin
    if(reset) begin valid_q<=0; out_valid<=0; end
    else begin
      valid_q<={valid_q[2:0],in_valid}; out_valid<=valid_q[3];
      if(in_valid) begin
        type_q[0]<=in_datatype; sa_q<=sa_d; sb_q<=sb_d; ea_q<=ea_d; eb_q<=eb_d; nan_s1_q<=na_d|nb_d;
      end
      for(i=1;i<4;i=i+1) if(valid_q[i-1]) type_q[i]<=type_q[i-1];
      if(valid_q[0]) begin coeff_q[1]<=coeff_d; scale_exp_q[1]<={1'b0,ea_q}+{1'b0,eb_q}; scale_nan_q[1]<=nan_s1_q; end
      for(i=2;i<4;i=i+1) if(valid_q[i-1]) begin
        coeff_q[i]<=coeff_q[i-1]; scale_exp_q[i]<=scale_exp_q[i-1]; scale_nan_q[i]<=scale_nan_q[i-1];
      end
      if(valid_q[3]) begin
        out_magnitude<=magnitude_d; out_negative<=negative_d; out_anchor<=anchor_d; special_q<=special_d;
        out_z<=(special_d==0 && type_q[3]!=`DP_DT_INT8) ? z_d : 0;
      end
    end
  end
endmodule
