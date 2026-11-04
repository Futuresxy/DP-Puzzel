`include "dp_defs.vh"
// One logical element of a packed 32-bit lane. INDEX is static, so synthesis
// removes unavailable T/H/Q routes. Combinational; S1 registers live in lane.
module dp_operand_unpack #(parameter integer INDEX=0)(
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [1:0] in_e1, input wire in_e2,
  output reg [`DP_NUM_W-1:0] out_number
);

  `include "dp_functions.vh"
  localparam [31:0] HALF_MASK=(1<<`DP_HALF_W)-1, QUARTER_MASK=(1<<`DP_QUARTER_W)-1,
    MX6_MASK=(1<<`DP_MX6_W)-1, EIGHTH_MASK=(1<<`DP_EIGHTH_W)-1;
  integer eb,fb,bias,raw,e,f;
  reg [31:0] magnitude_work,exponent_work;
  reg ieee_encoding,finite_nan;
  reg [`DP_NUM_W-1:0] n;
  always @* begin
    n=0; magnitude_work=0; exponent_work=0; raw=0; eb=0; fb=0; bias=0; e=0; f=0;
    ieee_encoding=0; finite_nan=0;
    case(in_datatype)
      `DP_DT_TF32: begin raw=in_data >> `DP_TF32_PAD; eb=`DP_FP32_E; fb=`DP_FP16_F; bias=`DP_FP32_BIAS; ieee_encoding=1; end
      `DP_DT_FP16: begin raw=(in_data >> (INDEX*`DP_HALF_W)) & HALF_MASK; eb=`DP_FP16_E; fb=`DP_FP16_F; bias=`DP_FP16_BIAS; ieee_encoding=1; end
      `DP_DT_BF16: begin raw=(in_data >> (INDEX*`DP_HALF_W)) & HALF_MASK; eb=`DP_BF16_E; fb=`DP_BF16_F; bias=`DP_BF16_BIAS; ieee_encoding=1; end
      `DP_DT_MX8_E4M3: begin raw=(in_data >> (INDEX*`DP_QUARTER_W)) & QUARTER_MASK; eb=`DP_MX8_E4_E; fb=`DP_MX8_E4_F; bias=`DP_MX8_E4_BIAS; finite_nan=1; end
      `DP_DT_MX8_E5M2: begin raw=(in_data >> (INDEX*`DP_QUARTER_W)) & QUARTER_MASK; eb=`DP_MX8_E5_E; fb=`DP_MX8_E5_F; bias=`DP_MX8_E5_BIAS; ieee_encoding=1; end
      `DP_DT_MX6_E3M2: begin raw=(in_data >> (INDEX*`DP_QUARTER_W+`DP_MX6_PAD)) & MX6_MASK; eb=`DP_MX6_E3_E; fb=`DP_MX6_E3_F; bias=`DP_MX6_E3_BIAS; end
      `DP_DT_MX6_E2M3: begin raw=(in_data >> (INDEX*`DP_QUARTER_W+`DP_MX6_PAD)) & MX6_MASK; eb=`DP_MX6_E2_E; fb=`DP_MX6_E2_F; bias=`DP_MX6_E2_BIAS; end
      default: raw=(in_data >> (INDEX*`DP_EIGHTH_W)) & EIGHTH_MASK;
    endcase
    if(INDEX<elements(in_datatype)) begin
      if(in_datatype==`DP_DT_INT8) begin
        raw=(in_data >> (INDEX*`DP_QUARTER_W)) & QUARTER_MASK;
        n[`DP_NUM_SIGN]=(raw & 128)!=0;
        magnitude_work=(n[`DP_NUM_SIGN] ? 256-raw : raw);
      end else if(in_datatype==`DP_DT_HIF4) begin
        n[`DP_NUM_SIGN]=(raw & 8)!=0;
        magnitude_work=((raw & 7) << in_e1[INDEX/`DP_E1_GRAIN]);
        exponent_work={31'b0,in_e2};
      end else if(in_datatype==`DP_DT_MXFP4 || in_datatype==`DP_DT_NVFP4) begin
        n[`DP_NUM_SIGN]=(raw & 8)!=0;
        case(raw & 7)
          0:magnitude_work=0; 1:magnitude_work=1; 2:magnitude_work=2; 3:magnitude_work=3;
          4:magnitude_work=4; 5:magnitude_work=6; 6:magnitude_work=8; 7:magnitude_work=12;
        endcase
      end else begin
        e=(raw >> fb) & ((1<<eb)-1); f=raw & ((1<<fb)-1);
        n[`DP_NUM_SIGN]=((raw >> (eb+fb)) & 1)!=0;
        exponent_work=(e==0 ? 1 : e);
        if((ieee_encoding && e==((1<<eb)-1) && f!=0) ||
           (finite_nan && e==((1<<eb)-1) && f==((1<<fb)-1))) begin
          n[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]=`DP_CLASS_NAN; exponent_work=1;
          n[`DP_NUM_SIGNAL]=ieee_encoding && ((f & (1<<(fb-1)))==0);
        end else if(ieee_encoding && e==((1<<eb)-1)) begin
          n[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]=`DP_CLASS_INF; exponent_work=1;
        end else begin
          magnitude_work=((e!=0 ? (1<<fb) : 0) | f);
          if(elements(in_datatype)==`DP_Q_LANES) begin
            exponent_work=((exponent_work)+`DP_Q_BIAS-bias);
            magnitude_work=magnitude_work << (`DP_SCALE_F-fb);
          end
        end
      end
      if(n[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]!=`DP_CLASS_INF && n[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]!=`DP_CLASS_NAN)
        n[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]=(magnitude_work==0) ? `DP_CLASS_ZERO : `DP_CLASS_FINITE;
    end
    n[`DP_NUM_MAG_LO+:`DP_MANT_W]=magnitude_work[`DP_MANT_W-1:0];
    n[`DP_NUM_EXP_LO+:`DP_EXP_W]=exponent_work[`DP_EXP_W-1:0];
    out_number=n;
  end
endmodule
