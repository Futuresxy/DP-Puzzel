// Pure Verilog constant/arithmetic helpers, included inside module scope.
  function automatic [`DP_SPECIAL_W-1:0] merge_special(input [`DP_SPECIAL_W-1:0] a,b);
    reg [`DP_SPECIAL_W-1:0] s;
    begin
    s=a|b;
    s[`DP_SP_INVALID]=s[`DP_SP_INVALID] | (s[`DP_SP_POS_INF] & s[`DP_SP_NEG_INF]);
    merge_special=s;
    end
  endfunction
  function automatic [`DP_SPECIAL_W-1:0] product_special(input [`DP_NUM_W-1:0] a,b);
    reg [`DP_SPECIAL_W-1:0] s;
    reg inf_value, zero_value;
    begin
    s=0;
    s[`DP_SP_NAN]=(a[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_NAN)||(b[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_NAN);
    inf_value=(a[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_INF)||(b[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_INF);
    zero_value=(a[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_ZERO)||(b[`DP_NUM_CLASS_LO +: `DP_NUM_CLASS_W]==`DP_CLASS_ZERO);
    s[`DP_SP_INVALID]=a[`DP_NUM_SIGNAL]|b[`DP_NUM_SIGNAL]|(inf_value & zero_value);
    if(inf_value && !zero_value && !s[`DP_SP_NAN]) begin
      s[`DP_SP_NEG_INF]=a[`DP_NUM_SIGN]^b[`DP_NUM_SIGN];
      s[`DP_SP_POS_INF]=!s[`DP_SP_NEG_INF];
    end
    product_special=s;
    end
  endfunction
  function automatic integer elements(input  [`DP_TYPE_W-1:0] t);
    begin
    case(t)
      `DP_DT_TF32: elements=1;
      `DP_DT_FP16,`DP_DT_BF16: elements=2;
      `DP_DT_MXFP4,`DP_DT_NVFP4,`DP_DT_HIF4: elements=`DP_E_LANES;
      default: elements=`DP_Q_LANES;
    endcase
    end
  endfunction
  function automatic  [`DP_SCALE_TYPE_W-1:0] scale_type(input  [`DP_TYPE_W-1:0] t);
    begin
    case(t)
      `DP_DT_MX8_E4M3,`DP_DT_MX8_E5M2,`DP_DT_MX6_E3M2,`DP_DT_MX6_E2M3,`DP_DT_MXFP4: scale_type=`DP_SC_E8M0;
      `DP_DT_NVFP4: scale_type=`DP_SC_E4M3;
      `DP_DT_HIF4: scale_type=`DP_SC_E6M2;
      default: scale_type=`DP_SC_NONE;
    endcase
    end
  endfunction
  function automatic integer element_bias(input  [`DP_TYPE_W-1:0] t);
    begin
    case(t)
      `DP_DT_TF32,`DP_DT_BF16: element_bias=`DP_FP32_BIAS;
      `DP_DT_FP16,`DP_DT_MX8_E4M3,`DP_DT_MX8_E5M2,`DP_DT_MX6_E3M2,`DP_DT_MX6_E2M3: element_bias=`DP_Q_BIAS;
      default: element_bias=0;
    endcase
    end
  endfunction
  function automatic integer product_fraction(input  [`DP_TYPE_W-1:0] t);
    begin
    case(t)
      `DP_DT_TF32,`DP_DT_FP16: product_fraction=2*`DP_FP16_F;
      `DP_DT_BF16: product_fraction=2*`DP_BF16_F;
      `DP_DT_HIF4: product_fraction=2*`DP_HIF_ELEMENT_F;
      `DP_DT_MXFP4,`DP_DT_NVFP4: product_fraction=2*`DP_E_ELEMENT_F;
      `DP_DT_INT8: product_fraction=0;
      default: product_fraction=2*`DP_SCALE_F;
    endcase
    end
  endfunction
  function automatic integer lane_fraction(input [`DP_TYPE_W-1:0] t, input integer local_w);
    integer lane_w;
    begin
      lane_w=local_w+1+$clog2(`DP_Q_LANES);
      if(t==`DP_DT_INT8) lane_fraction=lane_w-`DP_INT_PRODUCT_W-$clog2(`DP_Q_LANES);
      else if(elements(t)==`DP_E_LANES) lane_fraction=product_fraction(t)+`DP_E_GUARD+lane_w-(`DP_E_PAIR_W+`DP_E_GUARD+$clog2(`DP_E_LANES/2));
      else lane_fraction=local_w-2+$clog2(`DP_Q_LANES)-$clog2(elements(t));
    end
  endfunction
  function automatic integer group_fraction(input [`DP_TYPE_W-1:0] t,input integer local_w);
    integer f;
    begin
      f=lane_fraction(t,local_w);
      if(t==`DP_DT_NVFP4 || t==`DP_DT_HIF4) group_fraction=f+2*`DP_SCALE_F-2*`DP_SCALE_M;
      else group_fraction=f;
    end
  endfunction
  function automatic integer anchor_width(input integer mag_w);
    begin
    // Includes raw anchor, post-LZD minimum and final normalization growth.
    anchor_width=1+$clog2(((-`DP_MIN_RAW_ANCHOR+mag_w-1)>`DP_MAX_RAW_ANCHOR ? (-`DP_MIN_RAW_ANCHOR+mag_w-1) : `DP_MAX_RAW_ANCHOR)+1);
    end
  endfunction
