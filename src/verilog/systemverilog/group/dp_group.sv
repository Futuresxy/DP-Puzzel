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
  parameter integer LOCAL_W=dp_pkg::DEFAULT_LOCAL_W,
  parameter integer LANE_SOP_W=LOCAL_W+1+$clog2(dp_pkg::Q_LANES),
  parameter integer GROUP_W=LANE_SOP_W+$clog2(dp_pkg::LANES),
  parameter integer MAG_W=GROUP_W-1,
  parameter integer ANCHOR_W=dp_pkg::anchor_width(MAG_W)
)(
  input wire clock,reset,in_valid,
  input wire [dp_pkg::TYPE_W-1:0] in_datatype,
  input wire [dp_pkg::LANES*dp_pkg::LANE_W-1:0] in_a,in_b,
  input wire [dp_pkg::SCALE_W-1:0] in_scale_a,in_scale_b,
  input wire [dp_pkg::SCALE_TYPE_W-1:0] in_scale_datatype,
  input wire [3:0] in_e1_a,in_e1_b, input wire [1:0] in_e2_a,in_e2_b,
  output reg out_valid,out_negative,
  output reg [MAG_W-1:0] out_magnitude,
  output reg signed [ANCHOR_W-1:0] out_anchor,
  output reg [$clog2(MAG_W+1)-1:0] out_z,
  output dp_pkg::special_t out_special
);
  import dp_pkg::*;
  localparam integer COEFF_W=2*SCALE_M, SCALE_MAG_W=SCALE_SOP_W-1,
    STRUCTURAL_DROP=GROUP_W-SCALE_SOP_W, SCALE_PRODUCT_W=SCALE_MAG_W+COEFF_W,
    SCALE_LOW_PAD=MAG_W-SCALE_PRODUCT_W;
  reg [3:0] valid_q;
  reg [TYPE_W-1:0] type_q [0:3];
  wire [LANES*LANE_SOP_W-1:0] lane_sops;
  wire [LANES*(PRODUCT_EXP_W+1)-1:0] lane_candidates;
  wire [LANES-1:0] lane_active,lane_negative,lane_valid;
  wire [LANES*SPECIAL_W-1:0] lane_special;
  wire [PRODUCT_EXP_W-1:0] lane_anchor [LANES];
  wire signed [PRODUCT_EXP_W:0] group_max;
  wire max_active;
  for(genvar i=0;i<LANES;i=i+1) begin: g_lane
    wire [PRODUCT_EXP_W-1:0] candidate;
    special_t special_value;
    dp_lane #(.LOCAL_W(LOCAL_W)) lane(
      .clock(clock),.reset(reset),.in_valid(in_valid),.in_datatype(in_datatype),
      .in_a(in_a[i*LANE_W+:LANE_W]),.in_b(in_b[i*LANE_W+:LANE_W]),
      .in_e1_a(in_e1_a[i*2+:2]),.in_e1_b(in_e1_b[i*2+:2]),.in_e2_a(in_e2_a[i]),.in_e2_b(in_e2_b[i]),
      .out_candidate(candidate),.out_candidate_active(lane_active[i]),.in_group_max(group_max[PRODUCT_EXP_W-1:0]),
      .out_valid(lane_valid[i]),.out_sop(lane_sops[i*LANE_SOP_W+:LANE_SOP_W]),
      .out_anchor(lane_anchor[i]),.out_special(special_value),.out_all_negative(lane_negative[i]));
    assign lane_candidates[i*(PRODUCT_EXP_W+1)+:PRODUCT_EXP_W+1]={1'b0,candidate};
    assign lane_special[i*SPECIAL_W+:SPECIAL_W]=special_value;
  end
  dp_max_tree #(.N(LANES),.W(PRODUCT_EXP_W+1)) group_exponent_max(
    .in_values(lane_candidates),.in_active(lane_active),.out_max(group_max),.out_active(max_active));
  wire [SCALE_M-1:0] sa_d,sb_d;
  wire [EXP_W-1:0] ea_d,eb_d;
  wire na_d,nb_d;
  reg [SCALE_M-1:0] sa_q,sb_q;
  reg [EXP_W-1:0] ea_q,eb_q;
  reg nan_s1_q;
  wire [COEFF_W-1:0] coeff_d;
  reg [COEFF_W-1:0] coeff_q [1:3];
  reg [PRODUCT_EXP_W-1:0] scale_exp_q [1:3];
  reg scale_nan_q [1:3];
  dp_scale_unpack scale_unpack_a(.in_data(in_scale_a),.in_datatype(in_scale_datatype),.out_magnitude(sa_d),.out_exponent(ea_d),.out_nan(na_d));
  dp_scale_unpack scale_unpack_b(.in_data(in_scale_b),.in_datatype(in_scale_datatype),.out_magnitude(sb_d),.out_exponent(eb_d),.out_nan(nb_d));
  dp_mul_unsigned #(.A_W(SCALE_M),.B_W(SCALE_M)) scale_pair_mul(.in_a(sa_q),.in_b(sb_q),.out_product(coeff_d));
  wire signed [GROUP_W-1:0] group_sum;
  dp_sum_tree #(.N(LANES),.W(LANE_SOP_W)) group_sop_add(.in_values(lane_sops),.out_sum(group_sum));
  wire inject_scale=(type_q[3]==DT_NVFP4 || type_q[3]==DT_HIF4) && valid_q[3];
  // Both branches share the absolute value. NV/HiF compact the magnitude
  // by slicing off structural low zeros; their legal group sums fit SCALE_MAG_W.
  wire group_negative=group_sum[GROUP_W-1];
  wire [GROUP_W-1:0] absolute_sop=group_negative ? -group_sum : group_sum;
  wire [SCALE_MAG_W-1:0] compact_mag=inject_scale ? absolute_sop[STRUCTURAL_DROP+:SCALE_MAG_W] : '0;
  wire [COEFF_W-1:0] compact_coeff=inject_scale ? coeff_q[3] : '0;
  wire [SCALE_PRODUCT_W-1:0] scale_product;
  dp_scale_multiply group_scale_mul(.in_magnitude(compact_mag),.in_coefficient(compact_coeff),.out_product(scale_product));
  wire [MAG_W-1:0] magnitude_d=inject_scale ? {scale_product,{SCALE_LOW_PAD{1'b0}}} : absolute_sop[MAG_W-1:0];
  wire negative_d=group_negative || (group_sum==0 && (&lane_negative));
  wire [$clog2(MAG_W+1)-1:0] z_d;
  wire magnitude_active;
  dp_lzd #(.W(MAG_W)) group_leading_detect(.in_magnitude(magnitude_d),.out_count(z_d),.out_active(magnitude_active));
  special_t special_d,special_q,lane0,lane1;
  reg signed [ANCHOR_W-1:0] anchor_d;
  assign out_special=special_q;
  always @* begin
    lane0=lane_special[0+:SPECIAL_W]; lane1=lane_special[SPECIAL_W+:SPECIAL_W];
    special_d=merge_special(lane0,lane1);
    special_d.nan=special_d.nan | scale_nan_q[3];
    if(coeff_q[3]==0 && (special_d.positive_inf || special_d.negative_inf)) begin
      special_d.invalid=1; special_d.positive_inf=0; special_d.negative_inf=0;
    end
    anchor_d=ANCHOR_W'(int'(lane_anchor[0])-2*element_bias(type_q[3])-group_fraction(type_q[3],LOCAL_W)+MAG_W-1);
    if(scale_type(type_q[3])!=SC_NONE)
      anchor_d=anchor_d+ANCHOR_W'(int'(scale_exp_q[3])-2*SCALE_BIAS);
    if(!magnitude_active || special_d!='0 || type_q[3]==DT_INT8) anchor_d='0;
  end
  always @(posedge clock) begin
    if(reset) begin valid_q<='0; out_valid<=0; end
    else begin
      valid_q<={valid_q[2:0],in_valid}; out_valid<=valid_q[3];
      if(in_valid) begin
        type_q[0]<=in_datatype; sa_q<=sa_d; sb_q<=sb_d; ea_q<=ea_d; eb_q<=eb_d; nan_s1_q<=na_d|nb_d;
      end
      for(integer i=1;i<4;i=i+1) if(valid_q[i-1]) type_q[i]<=type_q[i-1];
      if(valid_q[0]) begin coeff_q[1]<=coeff_d; scale_exp_q[1]<={1'b0,ea_q}+{1'b0,eb_q}; scale_nan_q[1]<=nan_s1_q; end
      for(integer i=2;i<4;i=i+1) if(valid_q[i-1]) begin
        coeff_q[i]<=coeff_q[i-1]; scale_exp_q[i]<=scale_exp_q[i-1]; scale_nan_q[i]<=scale_nan_q[i-1];
      end
      if(valid_q[3]) begin
        out_magnitude<=magnitude_d; out_negative<=negative_d; out_anchor<=anchor_d; special_q<=special_d;
        out_z<=(special_d=='0 && type_q[3]!=DT_INT8) ? z_d : '0;
      end
    end
  end
endmodule
