`include "dp_defs.vh"
// Finite signed SOP -> FP32, RNE only. One rounding operation after the two
// architected RTZ cuts. Supports subnormals, ties, signed zero and overflow.
// Combinational S8 block; special-result selection is owned by the top.
// S8 finite path.
// Precision / signal | S | I                  | F
// ------------------ | - | ------------------ | --------------
// Input SOP (TC)     | 1 | SUM_W-GLOBAL_MAG_W | GLOBAL_MAG_W-1
// Rounded magnitude  | 0 | 1                  | 23
// Input coordinate is in_anchor. Output FP32 encodes sign/exponent/fraction 1/8/23.
module dp_fp32_round #(
  parameter integer SUM_W = 43,
  ANCHOR_W = 10,
  GLOBAL_MAG_W = 39
) (
  input wire signed [SUM_W-1:0] in_sum,
  input wire signed [ANCHOR_W-1:0] in_anchor,
  input wire in_negative_zero,
  output reg [`DP_FP32_W-1:0] out_bits
);
  integer i;

  `include "dp_functions.vh"
  localparam integer COUNT_W = $clog2(SUM_W + 1), ROUND_W = SUM_W + 1;
  wire sign_value = in_sum[SUM_W-1] || (in_sum == 0 && in_negative_zero);
  wire [SUM_W-1:0] magnitude = in_sum[SUM_W-1] ? -in_sum : in_sum;
  wire [COUNT_W-1:0] leading;
  wire active;
  dp_lzd #(
    .W(SUM_W)
  ) output_leading_detect (
    .in_magnitude(magnitude),
    .out_count(leading),
    .out_active(active)
  );
  localparam integer EXP_CALC_W = ANCHOR_W + 1;
  localparam integer WINDOW_OFFSET_INT = GLOBAL_MAG_W - 1;
  localparam signed [EXP_CALC_W-1:0] WINDOW_OFFSET = WINDOW_OFFSET_INT[EXP_CALC_W-1:0],
    MIN_EXP = `DP_FP32_MIN_E, MAX_EXP = `DP_FP32_MAX_E, BIAS = `DP_FP32_BIAS;
  reg signed [EXP_CALC_W-1:0] exponent_value, lsb_value, biased_exponent;
  integer shift_value, highest;
  reg [ROUND_W-1:0] rounded;
  reg guard_bit, sticky_bit;
  always @* begin
    highest = SUM_W - 1 - {{(32 - COUNT_W) {1'b0}}, leading};
    lsb_value = $signed({in_anchor[ANCHOR_W-1], in_anchor}) - WINDOW_OFFSET;
    exponent_value = lsb_value + $signed(highest[EXP_CALC_W-1:0]);
    shift_value = exponent_value >= MIN_EXP ? highest - (`DP_FP32_M - 1) :
      `DP_FP32_MIN_LSB - $signed({{(32 - EXP_CALC_W) {lsb_value[EXP_CALC_W-1]}}, lsb_value});
    rounded = 0;
    guard_bit = 0;
    sticky_bit = 0;
    if (shift_value <= 0) rounded = {1'b0, magnitude} << (-shift_value);
    else begin
      rounded = {1'b0, magnitude} >> shift_value;
      for (i = 0; i < SUM_W; i = i + 1) begin
        if (i == shift_value - 1) guard_bit = magnitude[i];
        if (i < shift_value - 1) sticky_bit = sticky_bit | magnitude[i];
      end
      if (guard_bit && (sticky_bit || rounded[0])) rounded = rounded + 1'b1;
    end
    biased_exponent = exponent_value + BIAS;
    out_bits = 0;
    out_bits[`DP_FP32_W-1] = sign_value;
    if (active) begin
      if (exponent_value >= MIN_EXP) begin
        if (rounded[`DP_FP32_M]) begin
          rounded = rounded >> 1;
          exponent_value = exponent_value + 1'b1;
        end
        if (exponent_value > MAX_EXP) out_bits = out_bits | `DP_FP32_INF;
        else begin
          biased_exponent = exponent_value + BIAS;
          out_bits[`DP_FP32_F+:`DP_FP32_E] = biased_exponent[`DP_FP32_E-1:0];
          out_bits[0+:`DP_FP32_F] = rounded[0+:`DP_FP32_F];
        end
      end else out_bits = out_bits | rounded[`DP_FP32_W-1:0];
    end
  end
endmodule
