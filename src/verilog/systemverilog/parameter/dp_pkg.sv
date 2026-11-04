// DP v1.4 format encodings and structural constants. No state or hardware here.
// Width knobs are module parameters; derived functions preserve the binary point.
package dp_pkg;
  localparam integer TYPE_W=4, SCALE_TYPE_W=2, C_TYPE_W=1;
  localparam logic [TYPE_W-1:0] DT_TF32=0, DT_FP16=1, DT_BF16=2,
    DT_MX8_E4M3=3, DT_MX8_E5M2=4, DT_MX6_E3M2=5, DT_MX6_E2M3=6,
    DT_MXFP4=7, DT_NVFP4=8, DT_HIF4=9, DT_INT8=10;
  localparam logic [SCALE_TYPE_W-1:0] SC_NONE=0, SC_E8M0=1, SC_E4M3=2, SC_E6M2=3;
  localparam logic CT_FP32=0, CT_INT32=1;
  localparam integer FP32_W=32, FP32_E=8, FP32_F=23, FP32_M=FP32_F+1,
    FP32_BIAS=127, FP32_MIN_E=1-FP32_BIAS, FP32_MAX_E=FP32_BIAS,
    FP32_MIN_LSB=FP32_MIN_E-FP32_F;
  localparam integer HALF_W=16, LANE_W=32, GROUP_H=4, LANES=2,
    Q_LANES=4, E_LANES=8, MUL_BANKS=2, MUL_HI=8, MUL_LO=4,
    MANT_W=11, EXP_W=8, PRODUCT_W=2*MANT_W, PRODUCT_EXP_W=EXP_W+1,
    SCALE_W=8, SCALE_F=3, SCALE_M=SCALE_F+1, SCALE_BIAS=127,
    HIF_SCALE_BIAS=48, E_PAIR_W=10, E_GUARD=2, INT_PRODUCT_W=16,
    SCALE_SOP_W=E_PAIR_W+E_GUARD+$clog2(Q_LANES)+$clog2(LANES),
    BASE_LATENCY=8, DEFAULT_LOCAL_W=27, DEFAULT_GLOBAL_W=40;
  localparam integer DEFAULT_K=16,
    FP16_E=5,
    FP16_F=10,
    FP16_BIAS=(1<<(FP16_E-1))-1,
    BF16_E=8,
    BF16_F=7,
    BF16_BIAS=(1<<(BF16_E-1))-1,
    TF32_PAD=FP32_W-1-FP32_E-FP16_F,
    QUARTER_W=HALF_W/2,
    EIGHTH_W=HALF_W/4,
    MX8_E4_E=4,
    MX8_E4_F=3,
    MX8_E4_BIAS=(1<<(MX8_E4_E-1))-1,
    MX8_E5_E=5,
    MX8_E5_F=2,
    MX8_E5_BIAS=(1<<(MX8_E5_E-1))-1,
    MX6_E3_E=3,
    MX6_E3_F=2,
    MX6_E3_BIAS=(1<<(MX6_E3_E-1))-1,
    MX6_E2_E=2,
    MX6_E2_F=3,
    MX6_E2_BIAS=(1<<(MX6_E2_E-1))-1,
    MX6_W=1+MX6_E3_E+MX6_E3_F,
    MX6_PAD=QUARTER_W-MX6_W,
    Q_EXP_W=5,
    Q_BIAS=(1<<(Q_EXP_W-1))-1,
    Q_MAX_E=(1<<Q_EXP_W)-2,
    E_ELEMENT_F=1,
    HIF_ELEMENT_F=2,
    E1_GRAIN=4,
    E2_GRAIN=8,
    SCALE_MAX_E=(1<<SCALE_W)-2,
    Q_GROUP_HEADROOM=2+$clog2(Q_LANES)+$clog2(LANES)-1;
  // Bounds include decoded finite scales and the largest Q product exponent.
  localparam integer MAX_RAW_ANCHOR=2*(Q_MAX_E-Q_BIAS)+2*(SCALE_MAX_E-SCALE_BIAS)+Q_GROUP_HEADROOM,
    MIN_RAW_ANCHOR=2*(1-Q_BIAS)-2*SCALE_BIAS+Q_GROUP_HEADROOM;
  localparam logic [FP32_W-1:0] FP32_QNAN=32'h7fc00000, FP32_INF=32'h7f800000;
  localparam logic [1:0] CLASS_ZERO=0, CLASS_FINITE=1, CLASS_INF=2, CLASS_NAN=3;
  typedef struct packed {
    logic negative;
    logic [MANT_W-1:0] magnitude;
    logic [EXP_W-1:0] exponent;
    logic [1:0] category;
    logic signaling;
  } number_t;
  typedef struct packed {
    logic nan, invalid, positive_inf, negative_inf;
  } special_t;
  localparam integer SPECIAL_W=$bits(special_t);
  localparam integer NUM_W=$bits(number_t), NUM_SIGNAL=0, NUM_CLASS_LO=1,
    NUM_CLASS_W=2, NUM_EXP_LO=NUM_CLASS_LO+NUM_CLASS_W,
    NUM_MAG_LO=NUM_EXP_LO+EXP_W, NUM_SIGN=NUM_W-1;
  function automatic special_t merge_special(input special_t a,b);
    special_t s;
    s=a|b;
    s.invalid=s.invalid | (s.positive_inf & s.negative_inf);
    return s;
  endfunction
  function automatic special_t product_special(input number_t a,b);
    special_t s;
    logic inf_value, zero_value;
    s='0;
    s.nan=(a.category==CLASS_NAN)||(b.category==CLASS_NAN);
    inf_value=(a.category==CLASS_INF)||(b.category==CLASS_INF);
    zero_value=(a.category==CLASS_ZERO)||(b.category==CLASS_ZERO);
    s.invalid=a.signaling|b.signaling|(inf_value & zero_value);
    if(inf_value && !zero_value && !s.nan) begin
      s.negative_inf=a.negative^b.negative;
      s.positive_inf=!s.negative_inf;
    end
    return s;
  endfunction
  function automatic integer elements(input logic [TYPE_W-1:0] t);
    case(t)
      DT_TF32: return 1;
      DT_FP16,DT_BF16: return LANES;
      DT_MXFP4,DT_NVFP4,DT_HIF4: return E_LANES;
      default: return Q_LANES;
    endcase
  endfunction
  function automatic logic [SCALE_TYPE_W-1:0] scale_type(input logic [TYPE_W-1:0] t);
    case(t)
      DT_MX8_E4M3,DT_MX8_E5M2,DT_MX6_E3M2,DT_MX6_E2M3,DT_MXFP4: return SC_E8M0;
      DT_NVFP4: return SC_E4M3;
      DT_HIF4: return SC_E6M2;
      default: return SC_NONE;
    endcase
  endfunction
  function automatic integer element_bias(input logic [TYPE_W-1:0] t);
    case(t)
      DT_TF32,DT_BF16: return FP32_BIAS;
      DT_FP16,DT_MX8_E4M3,DT_MX8_E5M2,DT_MX6_E3M2,DT_MX6_E2M3: return Q_BIAS;
      default: return 0;
    endcase
  endfunction
  function automatic integer product_fraction(input logic [TYPE_W-1:0] t);
    case(t)
      DT_TF32,DT_FP16: return 2*FP16_F;
      DT_BF16: return 2*BF16_F;
      DT_HIF4: return 2*HIF_ELEMENT_F;
      DT_MXFP4,DT_NVFP4: return 2*E_ELEMENT_F;
      DT_INT8: return 0;
      default: return 2*SCALE_F;
    endcase
  endfunction
  function automatic integer lane_fraction(input logic [TYPE_W-1:0] t,input integer local_w);
    integer lane_w;
    lane_w=local_w+1+$clog2(Q_LANES);
    if(t==DT_INT8) return lane_w-INT_PRODUCT_W-$clog2(Q_LANES);
    if(elements(t)==E_LANES)
      return product_fraction(t)+E_GUARD+lane_w-(E_PAIR_W+E_GUARD+$clog2(E_LANES/2));
    return local_w-2+$clog2(Q_LANES)-$clog2(elements(t));
  endfunction
  function automatic integer group_fraction(input logic [TYPE_W-1:0] t,input integer local_w);
    integer f;
    f=lane_fraction(t,local_w);
    if(t==DT_NVFP4 || t==DT_HIF4) return f+2*SCALE_F-2*SCALE_M;
    return f;
  endfunction
  function automatic integer anchor_width(input integer mag_w);
    // Includes raw anchor, post-LZD minimum and final normalization growth.
    return 1+$clog2(((-MIN_RAW_ANCHOR+mag_w-1)>MAX_RAW_ANCHOR ? (-MIN_RAW_ANCHOR+mag_w-1) : MAX_RAW_ANCHOR)+1);
  endfunction
endpackage
