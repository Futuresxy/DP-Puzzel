`include "dp_defs.vh"
// Two wide/narrow exponent-adder sets per lane, matching the mantissa banks.
// E products share one e2 sum; Q uses both sums, H/T only the wide sum.
// Unsigned integer exponent sums (F0), including HiF4 e2; no mantissa fields.
module dp_exponent_bank(
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [`DP_E_LANES*`DP_EXP_W-1:0] in_a,in_b,
  output wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] out_exponents
);
  localparam integer Q_EXP_W=`DP_Q_EXP_W;
  wire [`DP_PRODUCT_EXP_W-1:0] wide_sum [0:`DP_MUL_BANKS-1];
  wire [Q_EXP_W:0] narrow_sum [0:`DP_MUL_BANKS-1];
  genvar bank,i;
  generate for(bank=0;bank<`DP_MUL_BANKS;bank=bank+1) begin: g_bank
    reg [`DP_EXP_W-1:0] wide_a,wide_b;
    reg [Q_EXP_W-1:0] narrow_a,narrow_b;
    always @* begin
      wide_a=0; wide_b=0; narrow_a=0; narrow_b=0;
      if(in_enable) begin
        case(in_datatype)
          `DP_DT_TF32,`DP_DT_FP16,`DP_DT_BF16: if(in_datatype!=`DP_DT_TF32 || bank==0) begin
            wide_a=in_a[bank*`DP_EXP_W+:`DP_EXP_W]; wide_b=in_b[bank*`DP_EXP_W+:`DP_EXP_W];
          end
          `DP_DT_MXFP4,`DP_DT_NVFP4,`DP_DT_HIF4: if(bank==0) begin
            wide_a=in_a[0+:`DP_EXP_W]; wide_b=in_b[0+:`DP_EXP_W];
          end
          `DP_DT_INT8: begin end
          default: begin
            wide_a=in_a[(bank*2)*`DP_EXP_W+:`DP_EXP_W]; wide_b=in_b[(bank*2)*`DP_EXP_W+:`DP_EXP_W];
            narrow_a=in_a[(bank*2+1)*`DP_EXP_W+:Q_EXP_W]; narrow_b=in_b[(bank*2+1)*`DP_EXP_W+:Q_EXP_W];
          end
        endcase
      end
    end
    dp_exponent_add #(.W(`DP_EXP_W)) wide_add(.in_a(wide_a),.in_b(wide_b),.out_sum(wide_sum[bank]));
    dp_exponent_add #(.W(Q_EXP_W)) narrow_add(.in_a(narrow_a),.in_b(narrow_b),.out_sum(narrow_sum[bank]));
  end endgenerate
  generate for(i=0;i<`DP_E_LANES;i=i+1) begin: g_route
    wire is_e=(in_datatype==`DP_DT_MXFP4 || in_datatype==`DP_DT_NVFP4 || in_datatype==`DP_DT_HIF4);
    wire is_h=(in_datatype==`DP_DT_TF32 || in_datatype==`DP_DT_FP16 || in_datatype==`DP_DT_BF16);
    wire [`DP_PRODUCT_EXP_W-1:0] q_sum;
    if(i<`DP_Q_LANES && i%2==0) begin: g_even
      assign q_sum=wide_sum[i/2];
    end else if(i<`DP_Q_LANES) begin: g_odd
      assign q_sum={{(`DP_PRODUCT_EXP_W-Q_EXP_W-1){1'b0}},narrow_sum[i/2]};
    end else begin: g_unused
      assign q_sum=0;
    end
    if(i<`DP_MUL_BANKS) begin: g_h
      assign out_exponents[i*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W]=is_e ? wide_sum[0] : is_h ? wide_sum[i] : q_sum;
    end else begin: g_other
      assign out_exponents[i*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W]=is_e ? wide_sum[0] : is_h ? 0 : q_sum;
    end
  end endgenerate
endmodule
