// S5 combinational C decode. Raw C travels through S1-S4 without decoding.
// Both FP32 and INT32 produce sign plus M32; FP32 adds eight structural low zeros.
module dp_c_unpack #(parameter integer ANCHOR_W=10)(
  input wire [dp_pkg::FP32_W-1:0] in_data, input wire in_datatype,
  output reg out_negative,
  output reg [dp_pkg::FP32_W-1:0] out_magnitude,
  output reg signed [ANCHOR_W-1:0] out_anchor,
  output wire [$clog2(dp_pkg::FP32_W+1)-1:0] out_z,
  output dp_pkg::special_t out_special
);
  import dp_pkg::*;
  special_t special_d;
  wire [FP32_E-1:0] exponent=in_data[FP32_F+:FP32_E];
  wire [FP32_F-1:0] fraction=in_data[0+:FP32_F];
  wire [$clog2(FP32_W+1)-1:0] count;
  wire active;
  assign out_special=special_d;
  dp_lzd #(.W(FP32_W)) c_subnormal_detect(.in_magnitude(out_magnitude),.out_count(count),.out_active(active));
  assign out_z=in_datatype==CT_FP32 && special_d=='0 ? count : '0;
  always @* begin
    out_negative=in_data[FP32_W-1]; out_magnitude='0; out_anchor='0; special_d='0;
    if(in_datatype==CT_INT32) out_magnitude=out_negative ? -in_data : in_data;
    else if(&exponent) begin
      special_d.nan=|fraction;
      special_d.invalid=(|fraction) && !fraction[FP32_F-1];
      special_d.positive_inf=!(|fraction) && !out_negative;
      special_d.negative_inf=!(|fraction) && out_negative;
    end else begin
      out_magnitude={|exponent,fraction,{(FP32_W-FP32_M){1'b0}}};
      if(out_magnitude!=0) out_anchor=ANCHOR_W'((exponent==0 ? 1 : int'(exponent))-FP32_BIAS);
    end
  end
endmodule
