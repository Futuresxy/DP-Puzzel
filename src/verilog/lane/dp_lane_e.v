`include "dp_defs.vh"
// E8 lane: MXFP4/NVFP4/HiF4 only. S1 decode, S2 multiply/pair, S3 lane tree.
// S4's exact e2 left shift is combinational; the group owns its capture register.
// Synchronous active-high reset clears valid; data holds through bubbles.
// TC widths include S; I excludes S. Product sign travels separately.
// Precision     | Input S | I | F | Product S | I | F | Pair S | I | F | Lane S | I | F
// ------------- | ------- | - | - | --------- | - | - | ------ | - | - | ------ | - | -
// MXFP4/NVFP4   | 0       | 3 | 1 | 0         | 6 | 2 | 1      | 7 | 2 | 1      | 9 | 2
// HiF4 (e1 in)  | 0       | 2 | 2 | 0         | 4 | 4 | 1      | 5 | 4 | 1      | 7 | 4
// All E after S4 lane shift: TC S1I9F4, 14 bits. No exponent MAX/right shifter.
module dp_lane_e (
  // verilog_format: off
  input wire clock,reset,in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_LANE_W-1:0] in_a,in_b,
  input wire [1:0] in_e1_a,in_e1_b,
  input wire in_e2_a,in_e2_b,
  output wire out_valid,out_all_negative,
  output wire signed [13:0] out_sop
  // verilog_format: on
);
  localparam integer MANT_W = `DP_MUL_LO, PRODUCT_W = 2 * MANT_W, PAIRS = `DP_E_LANES / 2,
    PAIR_W = PRODUCT_W + 2, LANE_W = PAIR_W + $clog2(
    PAIRS
  ), FUSED_W = LANE_W + `DP_E_GUARD;
  reg [2:0] valid_q;
  reg [`DP_E_LANES*MANT_W-1:0] a_mantissa_s1_q, b_mantissa_s1_q;
  reg [`DP_E_LANES-1:0] a_sign_s1_q, b_sign_s1_q;
  reg [1:0] shift_s1_q, shift_s2_q, shift_s3_q;
  reg [PAIRS*PAIR_W-1:0] pairs_s2_q;
  reg all_negative_s2_q, all_negative_s3_q;
  reg signed [LANE_W-1:0] sop_s3_q;
  wire [`DP_E_LANES*MANT_W-1:0] a_mantissa_d, b_mantissa_d;
  wire [`DP_E_LANES-1:0] product_negative;
  wire [`DP_E_LANES*(PRODUCT_W+1)-1:0] signed_products;
  wire [PAIRS*PAIR_W-1:0] pairs_d;
  wire signed [LANE_W-1:0] lane_sum_d;
  function [MANT_W-1:0] decode_magnitude;
    input [3:0] raw;
    input hif, e1;
    begin
      if (hif) decode_magnitude = {1'b0, raw[2:0]} << e1;
      else
        case (raw[2:0])
          3'd0: decode_magnitude = 4'd0;
          3'd1: decode_magnitude = 4'd1;
          3'd2: decode_magnitude = 4'd2;
          3'd3: decode_magnitude = 4'd3;
          3'd4: decode_magnitude = 4'd4;
          3'd5: decode_magnitude = 4'd6;
          3'd6: decode_magnitude = 4'd8;
          default: decode_magnitude = 4'd12;
        endcase
    end
  endfunction
  genvar j;
  generate
    for (j = 0; j < `DP_E_LANES; j = j + 1) begin : g_product
      wire [PRODUCT_W-1:0] magnitude;
      wire signed [PRODUCT_W:0] positive_product = {1'b0, magnitude};
      assign a_mantissa_d[j*MANT_W+:MANT_W] = decode_magnitude(
        in_a[j*4+:4], in_datatype == `DP_DT_HIF4, in_e1_a[j/4]
      );
      assign b_mantissa_d[j*MANT_W+:MANT_W] = decode_magnitude(
        in_b[j*4+:4], in_datatype == `DP_DT_HIF4, in_e1_b[j/4]
      );
      dp_mul_unsigned #(
        .A_W(MANT_W),
        .B_W(MANT_W)
      ) element_mul (
        .in_a(a_mantissa_s1_q[j*MANT_W+:MANT_W]),
        .in_b(b_mantissa_s1_q[j*MANT_W+:MANT_W]),
        .out_product(magnitude)
      );
      assign product_negative[j] = a_sign_s1_q[j] ^ b_sign_s1_q[j];
      assign signed_products[j*(PRODUCT_W+1)+:PRODUCT_W+1] = product_negative[j] ?
        -positive_product : positive_product;
      always @(posedge clock)
        if (!reset && in_valid) begin
          a_sign_s1_q[j] <= in_a[j*4+3];
          b_sign_s1_q[j] <= in_b[j*4+3];
        end
    end
    for (j = 0; j < PAIRS; j = j + 1) begin : g_pair
      wire signed [PRODUCT_W:0] a = signed_products[2*j*(PRODUCT_W+1)+:PRODUCT_W+1];
      wire signed [PRODUCT_W:0] b = signed_products[(2*j+1)*(PRODUCT_W+1)+:PRODUCT_W+1];
      assign pairs_d[j*PAIR_W+:PAIR_W] = $signed({a[PRODUCT_W], a}) + $signed({b[PRODUCT_W], b});
    end
  endgenerate
  dp_sum_tree #(
    .N(PAIRS),
    .W(PAIR_W)
  ) lane_sop_tree (
    .in_values(pairs_s2_q),
    .out_sum  (lane_sum_d)
  );
  // Sign extension precedes the exact shift. MX/NV use a constant two low zeros.
  wire signed [FUSED_W-1:0] extended_sop = {{`DP_E_GUARD{sop_s3_q[LANE_W-1]}}, sop_s3_q};
  assign out_sop = extended_sop <<< shift_s3_q;
  assign out_valid = valid_q[2];
  assign out_all_negative = all_negative_s3_q;
  always @(posedge clock) begin
    if (reset) valid_q <= 0;
    else begin
      valid_q <= {valid_q[1:0], in_valid};
      if (in_valid) begin
        a_mantissa_s1_q <= a_mantissa_d;
        b_mantissa_s1_q <= b_mantissa_d;
        shift_s1_q <= in_datatype == `DP_DT_HIF4 ? {1'b0, in_e2_a} + {1'b0, in_e2_b} : 2'd2;
      end
      if (valid_q[0]) begin
        pairs_s2_q <= pairs_d;
        all_negative_s2_q <= &product_negative;
        shift_s2_q <= shift_s1_q;
      end
      if (valid_q[1]) begin
        sop_s3_q <= lane_sum_d;
        all_negative_s3_q <= all_negative_s2_q;
        shift_s3_q <= shift_s2_q;
      end
    end
  end
endmodule
