// S2 combinational lane multiplier bank: exactly two HH/HL/LH/LL sets.
// Muxes isolate unused multiplier operands. T/H partial products, Q/E independent
// products and the second INT8 split product share these physical instances.
module dp_mantissa_bank(
  input wire [dp_pkg::TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [dp_pkg::E_LANES*dp_pkg::MANT_W-1:0] in_a,in_b,
  output wire [dp_pkg::E_LANES*dp_pkg::PRODUCT_W-1:0] out_products
);
  import dp_pkg::*;
  wire [PRODUCT_W-1:0] result [MUL_BANKS][4];
  for(genvar bank=0;bank<MUL_BANKS;bank=bank+1) begin: g_bank
    reg [MUL_HI-1:0] hh_a,hh_b,hl_a,lh_b;
    reg [MUL_LO-1:0] hl_b,lh_a,ll_a,ll_b;
    wire [2*MUL_HI-1:0] hh;
    wire [MUL_HI+MUL_LO-1:0] hl,lh;
    wire [2*MUL_LO-1:0] ll;
    reg [PRODUCT_W-1:0] p0,p1,p2,p3;
    wire [MANT_W-1:0] a_h=in_a[bank*MANT_W+:MANT_W], b_h=in_b[bank*MANT_W+:MANT_W];
    wire [MANT_W-1:0] a_q0=in_a[(bank*2)*MANT_W+:MANT_W], b_q0=in_b[(bank*2)*MANT_W+:MANT_W];
    wire [MANT_W-1:0] a_q1=in_a[(bank*2+1)*MANT_W+:MANT_W], b_q1=in_b[(bank*2+1)*MANT_W+:MANT_W];
    always @* begin
      hh_a='0; hh_b='0; hl_a='0; hl_b='0; lh_a='0; lh_b='0; ll_a='0; ll_b='0;
      if(in_enable) begin
        case(in_datatype)
          DT_TF32,DT_FP16: if(in_datatype==DT_FP16 || bank==0) begin
            hh_a=MUL_HI'(a_h>>MUL_LO); hh_b=MUL_HI'(b_h>>MUL_LO);
            hl_a=hh_a; hl_b=MUL_LO'(b_h); lh_a=MUL_LO'(a_h); lh_b=hh_b;
            ll_a=MUL_LO'(a_h); ll_b=MUL_LO'(b_h);
          end
          DT_BF16: begin hh_a=MUL_HI'(a_h); hh_b=MUL_HI'(b_h); end
          DT_INT8: begin
            hh_a=MUL_HI'(a_q0); hh_b=MUL_HI'(b_q0);
            hl_a=MUL_HI'(a_q1); hl_b=MUL_LO'(b_q1);
            lh_a=MUL_LO'(b_q1>>MUL_LO); lh_b=MUL_HI'(a_q1);
          end
          DT_MXFP4,DT_NVFP4,DT_HIF4: begin
            hh_a=MUL_HI'(in_a[(bank*4)*MANT_W+:MANT_W]); hh_b=MUL_HI'(in_b[(bank*4)*MANT_W+:MANT_W]);
            hl_a=MUL_HI'(in_a[(bank*4+1)*MANT_W+:MANT_W]); hl_b=MUL_LO'(in_b[(bank*4+1)*MANT_W+:MANT_W]);
            lh_a=MUL_LO'(in_a[(bank*4+2)*MANT_W+:MANT_W]); lh_b=MUL_HI'(in_b[(bank*4+2)*MANT_W+:MANT_W]);
            ll_a=MUL_LO'(in_a[(bank*4+3)*MANT_W+:MANT_W]); ll_b=MUL_LO'(in_b[(bank*4+3)*MANT_W+:MANT_W]);
          end
          default: begin
            ll_a=MUL_LO'(a_q0); ll_b=MUL_LO'(b_q0);
            lh_a=MUL_LO'(a_q1); lh_b=MUL_HI'(b_q1);
          end
        endcase
      end
    end
    dp_mul_unsigned #(.A_W(MUL_HI),.B_W(MUL_HI)) hh_mul(.in_a(hh_a),.in_b(hh_b),.out_product(hh));
    dp_mul_unsigned #(.A_W(MUL_HI),.B_W(MUL_LO)) hl_mul(.in_a(hl_a),.in_b(hl_b),.out_product(hl));
    dp_mul_unsigned #(.A_W(MUL_LO),.B_W(MUL_HI)) lh_mul(.in_a(lh_a),.in_b(lh_b),.out_product(lh));
    dp_mul_unsigned #(.A_W(MUL_LO),.B_W(MUL_LO)) ll_mul(.in_a(ll_a),.in_b(ll_b),.out_product(ll));
    always @* begin
      p0='0; p1='0; p2='0; p3='0;
      case(in_datatype)
        DT_TF32,DT_FP16: p0=(PRODUCT_W'(hh)<<(2*MUL_LO))+((PRODUCT_W'(hl)+PRODUCT_W'(lh))<<MUL_LO)+PRODUCT_W'(ll);
        DT_BF16: p0=PRODUCT_W'(hh);
        DT_INT8: begin p0=PRODUCT_W'(hh); p1=PRODUCT_W'(hl)+(PRODUCT_W'(lh)<<MUL_LO); end
        DT_MXFP4,DT_NVFP4,DT_HIF4: begin p0=PRODUCT_W'(hh); p1=PRODUCT_W'(hl); p2=PRODUCT_W'(lh); p3=PRODUCT_W'(ll); end
        default: begin p0=PRODUCT_W'(ll); p1=PRODUCT_W'(lh); end
      endcase
    end
    assign result[bank][0]=p0; assign result[bank][1]=p1;
    assign result[bank][2]=p2; assign result[bank][3]=p3;
  end
  for(genvar i=0;i<E_LANES;i=i+1) begin: g_route
    if(i<2) begin: g_h
      assign out_products[i*PRODUCT_W+:PRODUCT_W]=(elements(in_datatype)<Q_LANES) ? result[i][0] :
        (elements(in_datatype)==Q_LANES) ? result[i/2][i%2] : result[i/4][i%4];
    end else if(i<Q_LANES) begin: g_q
      assign out_products[i*PRODUCT_W+:PRODUCT_W]=(elements(in_datatype)<Q_LANES) ? '0 :
        (elements(in_datatype)==Q_LANES) ? result[i/2][i%2] : result[i/4][i%4];
    end else begin: g_e
      assign out_products[i*PRODUCT_W+:PRODUCT_W]=(elements(in_datatype)==E_LANES) ? result[i/4][i%4] : '0;
    end
  end
endmodule
