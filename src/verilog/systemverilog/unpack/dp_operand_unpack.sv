// One logical element of a packed 32-bit lane. INDEX is static, so synthesis
// removes unavailable T/H/Q routes. Combinational; S1 registers live in lane.
module dp_operand_unpack #(parameter integer INDEX=0)(
  input wire [dp_pkg::LANE_W-1:0] in_data,
  input wire [dp_pkg::TYPE_W-1:0] in_datatype,
  input wire [1:0] in_e1, input wire in_e2,
  output dp_pkg::number_t out_number
);
  import dp_pkg::*;
  localparam [31:0] HALF_MASK=(1<<HALF_W)-1, QUARTER_MASK=(1<<QUARTER_W)-1,
    MX6_MASK=(1<<MX6_W)-1, EIGHTH_MASK=(1<<EIGHTH_W)-1;
  integer eb,fb,bias,raw,e,f;
  logic ieee_encoding,finite_nan;
  number_t n;
  always @* begin
    n='0; raw=0; eb=0; fb=0; bias=0; e=0; f=0;
    ieee_encoding=0; finite_nan=0;
    case(in_datatype)
      DT_TF32: begin raw=in_data >> TF32_PAD; eb=FP32_E; fb=FP16_F; bias=FP32_BIAS; ieee_encoding=1; end
      DT_FP16: begin raw=(in_data >> (INDEX*HALF_W)) & HALF_MASK; eb=FP16_E; fb=FP16_F; bias=FP16_BIAS; ieee_encoding=1; end
      DT_BF16: begin raw=(in_data >> (INDEX*HALF_W)) & HALF_MASK; eb=BF16_E; fb=BF16_F; bias=BF16_BIAS; ieee_encoding=1; end
      DT_MX8_E4M3: begin raw=(in_data >> (INDEX*QUARTER_W)) & QUARTER_MASK; eb=MX8_E4_E; fb=MX8_E4_F; bias=MX8_E4_BIAS; finite_nan=1; end
      DT_MX8_E5M2: begin raw=(in_data >> (INDEX*QUARTER_W)) & QUARTER_MASK; eb=MX8_E5_E; fb=MX8_E5_F; bias=MX8_E5_BIAS; ieee_encoding=1; end
      DT_MX6_E3M2: begin raw=(in_data >> (INDEX*QUARTER_W+MX6_PAD)) & MX6_MASK; eb=MX6_E3_E; fb=MX6_E3_F; bias=MX6_E3_BIAS; end
      DT_MX6_E2M3: begin raw=(in_data >> (INDEX*QUARTER_W+MX6_PAD)) & MX6_MASK; eb=MX6_E2_E; fb=MX6_E2_F; bias=MX6_E2_BIAS; end
      default: raw=(in_data >> (INDEX*EIGHTH_W)) & EIGHTH_MASK;
    endcase
    if(INDEX<elements(in_datatype)) begin
      if(in_datatype==DT_INT8) begin
        raw=(in_data >> (INDEX*QUARTER_W)) & QUARTER_MASK;
        n.negative=(raw & 128)!=0;
        n.magnitude=MANT_W'(n.negative ? 256-raw : raw);
      end else if(in_datatype==DT_HIF4) begin
        n.negative=(raw & 8)!=0;
        n.magnitude=MANT_W'((raw & 7) << in_e1[INDEX/E1_GRAIN]);
        n.exponent=EXP_W'(in_e2);
      end else if(in_datatype==DT_MXFP4 || in_datatype==DT_NVFP4) begin
        n.negative=(raw & 8)!=0;
        case(raw & 7)
          0:n.magnitude=0; 1:n.magnitude=1; 2:n.magnitude=2; 3:n.magnitude=3;
          4:n.magnitude=4; 5:n.magnitude=6; 6:n.magnitude=8; 7:n.magnitude=12;
        endcase
      end else begin
        e=(raw >> fb) & ((1<<eb)-1); f=raw & ((1<<fb)-1);
        n.negative=((raw >> (eb+fb)) & 1)!=0;
        n.exponent=EXP_W'(e==0 ? 1 : e);
        if((ieee_encoding && e==((1<<eb)-1) && f!=0) ||
           (finite_nan && e==((1<<eb)-1) && f==((1<<fb)-1))) begin
          n.category=CLASS_NAN; n.exponent=1;
          n.signaling=ieee_encoding && ((f & (1<<(fb-1)))==0);
        end else if(ieee_encoding && e==((1<<eb)-1)) begin
          n.category=CLASS_INF; n.exponent=1;
        end else begin
          n.magnitude=MANT_W'((e!=0 ? (1<<fb) : 0) | f);
          if(elements(in_datatype)==Q_LANES) begin
            n.exponent=EXP_W'(int'(n.exponent)+Q_BIAS-bias);
            n.magnitude=n.magnitude << (SCALE_F-fb);
          end
        end
      end
      if(n.category!=CLASS_INF && n.category!=CLASS_NAN)
        n.category=(n.magnitude==0) ? CLASS_ZERO : CLASS_FINITE;
    end
    out_number=n;
  end
endmodule
