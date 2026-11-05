`include "dp_defs.vh"
// S5 combinational C decode. Raw C travels through S1-S4 without decoding.
// Both FP32 and INT32 produce sign plus M32; FP32 adds eight structural low zeros.
// FP32 M24 S0I1F23 -> M32 S0I1F31. INT32 absolute value S0I32F0.
// Both carry a separate sign. Anchor and LZD count are integer sidebands.
module dp_c_unpack #(
  parameter integer ANCHOR_W = 10
) (
  input wire [`DP_FP32_W-1:0] in_data,
  input wire in_datatype,
  output reg out_negative,
  output reg [`DP_FP32_W-1:0] out_magnitude,
  output reg signed [ANCHOR_W-1:0] out_anchor,
  output wire [$clog2(`DP_FP32_W+1)-1:0] out_z,
  output wire [`DP_SPECIAL_W-1:0] out_special
);

  `include "dp_functions.vh"
  reg [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_FP32_E-1:0] exponent = in_data[`DP_FP32_F+:`DP_FP32_E];
  wire [`DP_FP32_F-1:0] fraction = in_data[0+:`DP_FP32_F];
  wire [$clog2(`DP_FP32_W+1)-1:0] count;
  wire active;
  assign out_special = special_d;
  dp_lzd #(
    .W(`DP_FP32_W)
  ) c_subnormal_detect (
    .in_magnitude(out_magnitude),
    .out_count(count),
    .out_active(active)
  );
  assign out_z = in_datatype == `DP_CT_FP32 && special_d == 0 ? count : 0;
  reg signed [ANCHOR_W-1:0] exponent_unbiased;
  localparam signed [ANCHOR_W-1:0] BIAS = `DP_FP32_BIAS;
  always @* begin
    exponent_unbiased = $signed({{(ANCHOR_W - `DP_FP32_E) {1'b0}}, exponent}) - BIAS;
    if (exponent == 0) exponent_unbiased = 1 - BIAS;
    out_negative = in_data[`DP_FP32_W-1];
    out_magnitude = 0;
    out_anchor = 0;
    special_d = 0;
    if (in_datatype == `DP_CT_INT32) out_magnitude = out_negative ? -in_data : in_data;
    else if (&exponent) begin
      special_d[`DP_SP_NAN] = |fraction;
      special_d[`DP_SP_INVALID] = (|fraction) && !fraction[`DP_FP32_F-1];
      special_d[`DP_SP_POS_INF] = !(|fraction) && !out_negative;
      special_d[`DP_SP_NEG_INF] = !(|fraction) && out_negative;
    end else begin
      out_magnitude = {|exponent, fraction, {(`DP_FP32_W - `DP_FP32_M) {1'b0}}};
      if (out_magnitude != 0) out_anchor = exponent_unbiased;
    end
  end
endmodule
