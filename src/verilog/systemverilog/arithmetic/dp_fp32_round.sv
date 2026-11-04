// Finite signed SOP -> FP32, RNE only. One rounding operation after the two
// architected RTZ cuts. Supports subnormals, ties, signed zero and overflow.
// Combinational S8 block; special-result selection is owned by the top.
module dp_fp32_round #(
  parameter integer SUM_W=43, ANCHOR_W=10, GLOBAL_MAG_W=39
)(
  input wire signed [SUM_W-1:0] in_sum,
  input wire signed [ANCHOR_W-1:0] in_anchor,
  input wire in_negative_zero,
  output reg [dp_pkg::FP32_W-1:0] out_bits
);
  import dp_pkg::*;
  localparam integer COUNT_W=$clog2(SUM_W+1), ROUND_W=SUM_W+1;
  wire sign_value=in_sum[SUM_W-1] || (in_sum==0 && in_negative_zero);
  wire [SUM_W-1:0] magnitude=in_sum[SUM_W-1] ? -in_sum : in_sum;
  wire [COUNT_W-1:0] leading;
  wire active;
  dp_lzd #(.W(SUM_W)) output_leading_detect(.in_magnitude(magnitude),.out_count(leading),.out_active(active));
  reg signed [ANCHOR_W:0] exponent_value,lsb_value;
  integer shift_value,highest;
  reg [ROUND_W-1:0] rounded;
  reg guard_bit,sticky_bit;
  always @* begin
    highest=SUM_W-1-int'(leading);
    lsb_value=(ANCHOR_W+1)'(in_anchor)-(ANCHOR_W+1)'(GLOBAL_MAG_W-1);
    exponent_value=lsb_value+(ANCHOR_W+1)'(highest);
    shift_value=exponent_value>=(ANCHOR_W+1)'(FP32_MIN_E) ? highest-(FP32_M-1) : FP32_MIN_LSB-int'(lsb_value);
    rounded='0; guard_bit=0; sticky_bit=0;
    if(shift_value<=0) rounded=ROUND_W'(magnitude)<<(-shift_value);
    else begin
      rounded=ROUND_W'(magnitude)>>shift_value;
      for(integer i=0;i<SUM_W;i=i+1) begin
        if(i==shift_value-1) guard_bit=magnitude[i];
        if(i<shift_value-1) sticky_bit=sticky_bit|magnitude[i];
      end
      if(guard_bit && (sticky_bit || rounded[0])) rounded=rounded+1'b1;
    end
    out_bits='0; out_bits[FP32_W-1]=sign_value;
    if(active) begin
      if(exponent_value>=(ANCHOR_W+1)'(FP32_MIN_E)) begin
        if(rounded[FP32_M]) begin rounded=rounded>>1; exponent_value=exponent_value+1'b1; end
        if(exponent_value>(ANCHOR_W+1)'(FP32_MAX_E)) out_bits=out_bits|FP32_INF;
        else begin
          out_bits[FP32_F+:FP32_E]=FP32_E'(int'(exponent_value)+FP32_BIAS);
          out_bits[0+:FP32_F]=rounded[0+:FP32_F];
        end
      end else out_bits=out_bits|FP32_W'(rounded);
    end
  end
endmodule
