
// Two wide/narrow exponent-adder sets per lane, matching the mantissa banks.
// E products share one e2 sum; Q uses both sums, H/T only the wide sum.
module dp_exponent_bank(
  input wire [dp_pkg::TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [dp_pkg::E_LANES*dp_pkg::EXP_W-1:0] in_a,in_b,
  output wire [dp_pkg::E_LANES*dp_pkg::PRODUCT_EXP_W-1:0] out_exponents
);
  localparam integer Q_EXP_W=dp_pkg::Q_EXP_W;
  wire [dp_pkg::PRODUCT_EXP_W-1:0] wide_sum [0:dp_pkg::MUL_BANKS-1];
  wire [Q_EXP_W:0] narrow_sum [0:dp_pkg::MUL_BANKS-1];
  genvar bank,i;
  generate for(bank=0;bank<dp_pkg::MUL_BANKS;bank=bank+1) begin: g_bank
    reg [dp_pkg::EXP_W-1:0] wide_a,wide_b;
    reg [Q_EXP_W-1:0] narrow_a,narrow_b;
    always @* begin
      wide_a=0; wide_b=0; narrow_a=0; narrow_b=0;
      if(in_enable) begin
        case(in_datatype)
          dp_pkg::DT_TF32,dp_pkg::DT_FP16,dp_pkg::DT_BF16: if(in_datatype!=dp_pkg::DT_TF32 || bank==0) begin
            wide_a=in_a[bank*dp_pkg::EXP_W+:dp_pkg::EXP_W]; wide_b=in_b[bank*dp_pkg::EXP_W+:dp_pkg::EXP_W];
          end
          dp_pkg::DT_MXFP4,dp_pkg::DT_NVFP4,dp_pkg::DT_HIF4: if(bank==0) begin
            wide_a=in_a[0+:dp_pkg::EXP_W]; wide_b=in_b[0+:dp_pkg::EXP_W];
          end
          dp_pkg::DT_INT8: begin end
          default: begin
            wide_a=in_a[(bank*2)*dp_pkg::EXP_W+:dp_pkg::EXP_W]; wide_b=in_b[(bank*2)*dp_pkg::EXP_W+:dp_pkg::EXP_W];
            narrow_a=in_a[(bank*2+1)*dp_pkg::EXP_W+:Q_EXP_W]; narrow_b=in_b[(bank*2+1)*dp_pkg::EXP_W+:Q_EXP_W];
          end
        endcase
      end
    end
    dp_exponent_add #(.W(dp_pkg::EXP_W)) wide_add(.in_a(wide_a),.in_b(wide_b),.out_sum(wide_sum[bank]));
    dp_exponent_add #(.W(Q_EXP_W)) narrow_add(.in_a(narrow_a),.in_b(narrow_b),.out_sum(narrow_sum[bank]));
  end endgenerate
  generate for(i=0;i<dp_pkg::E_LANES;i=i+1) begin: g_route
    wire is_e=(in_datatype==dp_pkg::DT_MXFP4 || in_datatype==dp_pkg::DT_NVFP4 || in_datatype==dp_pkg::DT_HIF4);
    wire is_h=(in_datatype==dp_pkg::DT_TF32 || in_datatype==dp_pkg::DT_FP16 || in_datatype==dp_pkg::DT_BF16);
    wire [dp_pkg::PRODUCT_EXP_W-1:0] q_sum;
    if(i<dp_pkg::Q_LANES && i%2==0) begin: g_even
      assign q_sum=wide_sum[i/2];
    end else if(i<dp_pkg::Q_LANES) begin: g_odd
      assign q_sum={{(dp_pkg::PRODUCT_EXP_W-Q_EXP_W-1){1'b0}},narrow_sum[i/2]};
    end else begin: g_unused
      assign q_sum=0;
    end
    if(i<dp_pkg::MUL_BANKS) begin: g_h
      assign out_exponents[i*dp_pkg::PRODUCT_EXP_W+:dp_pkg::PRODUCT_EXP_W]=is_e ? wide_sum[0] : is_h ? wide_sum[i] : q_sum;
    end else begin: g_other
      assign out_exponents[i*dp_pkg::PRODUCT_EXP_W+:dp_pkg::PRODUCT_EXP_W]=is_e ? wide_sum[0] : is_h ? 0 : q_sum;
    end
  end endgenerate
endmodule
