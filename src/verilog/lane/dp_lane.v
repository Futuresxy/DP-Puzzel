`include "dp_defs.vh"
// T1H2Q4E8. Owns S1 unpack, S2 products, S3 shared magnitude alignment,
// S4 lane tree. Common group MAX is a combinational S2 side interface.
// Synchronous high reset clears valid only; invalid data registers hold.
module dp_lane #(
  parameter integer LOCAL_W=`DP_DEFAULT_LOCAL_W,
  parameter integer LEAF_W=LOCAL_W+1,
  parameter integer LANE_SOP_W=LEAF_W+$clog2(`DP_Q_LANES)
)(
  input wire clock,reset,in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANE_W-1:0] in_a,in_b,
  input wire [1:0] in_e1_a,in_e1_b, input wire in_e2_a,in_e2_b,
  output wire [`DP_PRODUCT_EXP_W-1:0] out_candidate,
  output wire out_candidate_active,
  input wire [`DP_PRODUCT_EXP_W-1:0] in_group_max,
  output wire out_valid,
  output reg signed [LANE_SOP_W-1:0] out_sop,
  output reg [`DP_PRODUCT_EXP_W-1:0] out_anchor,
  output wire [`DP_SPECIAL_W-1:0] out_special,
  output reg out_all_negative
);
  genvar gen_i,j;
  integer i;

  `include "dp_functions.vh"
  reg [3:0] valid_q;
  reg [`DP_TYPE_W-1:0] type_s1_q,type_s2_q,type_s3_q;
  wire [`DP_E_LANES*`DP_NUM_W-1:0] a_numbers,b_numbers;
  wire [`DP_E_LANES*`DP_MANT_W-1:0] a_magnitude,b_magnitude;
  wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] products_d;
  reg [`DP_E_LANES*`DP_PRODUCT_W-1:0] products_q;
  wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] exponents_d;
  wire [`DP_E_LANES*`DP_EXP_W-1:0] a_exponents,b_exponents;
  reg [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] exponents_q;
  wire [`DP_E_LANES-1:0] negative_d,active_d;
  reg [`DP_E_LANES-1:0] negative_q,active_q;
  wire [`DP_E_LANES*`DP_SPECIAL_W-1:0] specials_d;
  reg [`DP_SPECIAL_W-1:0] special_d,special_s2_q,special_s3_q,special_s4_q,one_special;
  reg all_negative_d,all_negative_s2_q,all_negative_s3_q;
  reg [`DP_PRODUCT_EXP_W-1:0] anchor_s2_q,anchor_s3_q;
  wire [`DP_Q_LANES*LEAF_W-1:0] leaves_d;
  reg [`DP_Q_LANES*LEAF_W-1:0] leaves_q;
  wire signed [LANE_SOP_W-1:0] lane_sum;
  assign out_valid=valid_q[3];
  assign out_special=special_s4_q;
  dp_lane_unpack operand_unpack_a(.clock(clock),.reset(reset),.in_valid(in_valid),
    .in_datatype(in_datatype),.in_registered_datatype(type_s1_q),.in_data(in_a),
    .in_e1(in_e1_a),.in_e2(in_e2_a),.out_numbers(a_numbers));
  dp_lane_unpack operand_unpack_b(.clock(clock),.reset(reset),.in_valid(in_valid),
    .in_datatype(in_datatype),.in_registered_datatype(type_s1_q),.in_data(in_b),
    .in_e1(in_e1_b),.in_e2(in_e2_b),.out_numbers(b_numbers));
  generate
  for(gen_i=0;gen_i<`DP_E_LANES;gen_i=gen_i+1) begin: g_element
    wire [`DP_NUM_W-1:0] a_q,b_q;
    wire [`DP_SPECIAL_W-1:0] p_special;
    assign a_q=a_numbers[gen_i*`DP_NUM_W+:`DP_NUM_W];
    assign b_q=b_numbers[gen_i*`DP_NUM_W+:`DP_NUM_W];
    assign a_magnitude[gen_i*`DP_MANT_W+:`DP_MANT_W]=a_q[`DP_NUM_MAG_LO +: `DP_MANT_W];
    assign b_magnitude[gen_i*`DP_MANT_W+:`DP_MANT_W]=b_q[`DP_NUM_MAG_LO +: `DP_MANT_W];
    assign a_exponents[gen_i*`DP_EXP_W+:`DP_EXP_W]=a_q[`DP_NUM_EXP_LO+:`DP_EXP_W];
    assign b_exponents[gen_i*`DP_EXP_W+:`DP_EXP_W]=b_q[`DP_NUM_EXP_LO+:`DP_EXP_W];
    assign negative_d[gen_i]=a_q[`DP_NUM_SIGN]^b_q[`DP_NUM_SIGN];
    assign p_special=product_special(a_q,b_q);
    assign specials_d[gen_i*`DP_SPECIAL_W+:`DP_SPECIAL_W]=p_special;
    assign active_d[gen_i]=(a_q[`DP_NUM_MAG_LO +: `DP_MANT_W]!=0 && b_q[`DP_NUM_MAG_LO +: `DP_MANT_W]!=0 && p_special==0 && gen_i<elements(type_s1_q));
  end endgenerate
  dp_exponent_bank exponent_add(.in_datatype(type_s1_q),.in_enable(valid_q[0]),
    .in_a(a_exponents),.in_b(b_exponents),.out_exponents(exponents_d));
  // Exponent MAX does not depend on multiplier outputs or returned group MAX.
  wire [`DP_E_LANES*(`DP_PRODUCT_EXP_W+1)-1:0] max_candidates;
  wire signed [`DP_PRODUCT_EXP_W:0] lane_max;
  generate
  for(gen_i=0;gen_i<`DP_E_LANES;gen_i=gen_i+1) begin: g_candidate
    assign max_candidates[gen_i*(`DP_PRODUCT_EXP_W+1)+:`DP_PRODUCT_EXP_W+1]={1'b0,exponents_d[gen_i*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W]};
  end endgenerate
  dp_max_tree #(.N(`DP_E_LANES),.W(`DP_PRODUCT_EXP_W+1)) lane_exponent_max(
    .in_values(max_candidates),.in_active(active_d),.out_max(lane_max),.out_active(out_candidate_active));
  assign out_candidate=lane_max[`DP_PRODUCT_EXP_W-1:0];
  dp_mantissa_bank mantissa_mul_bank(.in_datatype(type_s1_q),.in_enable(valid_q[0]),
    .in_a(a_magnitude),.in_b(b_magnitude),.out_products(products_d));
  always @* begin
    special_d=0; all_negative_d=1; one_special=0;
    for(i=0;i<`DP_E_LANES;i=i+1) begin
      if(i<elements(type_s1_q)) begin
        one_special=specials_d[i*`DP_SPECIAL_W+:`DP_SPECIAL_W];
        special_d=merge_special(special_d,one_special);
        all_negative_d=all_negative_d & negative_d[i];
      end
    end
  end
  generate
  for(j=0;j<`DP_Q_LANES;j=j+1) begin: g_align
    reg [LOCAL_W-1:0] shift_input;
    reg [`DP_PRODUCT_EXP_W-1:0] delta;
    reg sign_value;
    reg signed [`DP_E_PAIR_W-1:0] pair_a,pair_b,pair_sum;
    reg [`DP_E_PAIR_W-1:0] pair_abs;
    wire [LOCAL_W-1:0] shifted;
    wire [`DP_PRODUCT_W-1:0] product_value=products_q[j*`DP_PRODUCT_W+:`DP_PRODUCT_W];
    always @* begin
      shift_input=0; delta=0; sign_value=0;
      pair_a=0; pair_b=0; pair_sum=0; pair_abs=0;
      if(valid_q[1]) begin
        if(elements(type_s2_q)==`DP_E_LANES) begin
          pair_a=products_q[(2*j)*`DP_PRODUCT_W+:`DP_E_PAIR_W];
          pair_b=products_q[(2*j+1)*`DP_PRODUCT_W+:`DP_E_PAIR_W];
          if(negative_q[2*j]) pair_a=-pair_a;
          if(negative_q[2*j+1]) pair_b=-pair_b;
          pair_sum=pair_a+pair_b; sign_value=pair_sum[`DP_E_PAIR_W-1];
          pair_abs=sign_value ? -pair_sum : pair_sum;
          // Guard zeros make the HiF e2 shift (0..2) exact.
          shift_input={{(LOCAL_W-`DP_E_PAIR_W){1'b0}},pair_abs} << (LEAF_W-`DP_E_PAIR_W);
          if(type_s2_q==`DP_DT_HIF4 && pair_abs!=0)
            delta=anchor_s2_q-exponents_q[(2*j)*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W];
        end else if(j<elements(type_s2_q)) begin
          sign_value=negative_q[j];
          if(type_s2_q==`DP_DT_INT8)
            shift_input={{(LOCAL_W-`DP_PRODUCT_W){1'b0}},product_value} << (LEAF_W-`DP_INT_PRODUCT_W);
          else if(active_q[j]) begin
            shift_input={{(LOCAL_W-`DP_PRODUCT_W){1'b0}},product_value} << (LOCAL_W-2-product_fraction(type_s2_q));
            delta=anchor_s2_q-exponents_q[j*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W];
          end
        end
      end
    end
    dp_rtz_shift #(.W(LOCAL_W),.SHIFT_W(`DP_PRODUCT_EXP_W)) local_align_shift(
      .in_magnitude(shift_input),.in_shift(delta),.out_magnitude(shifted));
    assign leaves_d[j*LEAF_W+:LEAF_W]=sign_value ? -$signed({1'b0,shifted}) : $signed({1'b0,shifted});
  end endgenerate
  dp_sum_tree #(.N(`DP_Q_LANES),.W(LEAF_W)) lane_sop_tree(.in_values(leaves_q),.out_sum(lane_sum));
  always @(posedge clock) begin
    if(reset) valid_q<=0;
    else begin
      valid_q<={valid_q[2:0],in_valid};
      if(in_valid) type_s1_q<=in_datatype;
      if(valid_q[0]) begin
        products_q<=products_d; exponents_q<=exponents_d; negative_q<=negative_d; active_q<=active_d;
        anchor_s2_q<=in_group_max; type_s2_q<=type_s1_q;
        special_s2_q<=special_d; all_negative_s2_q<=all_negative_d;
      end
      if(valid_q[1]) begin
        leaves_q<=leaves_d; anchor_s3_q<=anchor_s2_q; type_s3_q<=type_s2_q;
        special_s3_q<=special_s2_q; all_negative_s3_q<=all_negative_s2_q;
      end
      if(valid_q[2]) begin
        case(type_s3_q)
          `DP_DT_TF32: out_sop<=lane_sum << $clog2(`DP_Q_LANES);
          `DP_DT_FP16,`DP_DT_BF16: out_sop<=lane_sum << ($clog2(`DP_Q_LANES)-1);
          default: out_sop<=lane_sum;
        endcase
        out_anchor<=anchor_s3_q; special_s4_q<=special_s3_q; out_all_negative<=all_negative_s3_q;
      end
    end
  end
endmodule
