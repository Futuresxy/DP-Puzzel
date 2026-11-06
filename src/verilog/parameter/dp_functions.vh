// Pure Verilog constant/arithmetic helpers, included inside module scope.
function automatic [`DP_SPECIAL_W-1:0] merge_special(input [`DP_SPECIAL_W-1:0] operand_a,
                                                     input [`DP_SPECIAL_W-1:0] operand_b);
  reg [`DP_SPECIAL_W-1:0] special_flags;
  begin
    special_flags = operand_a | operand_b;
    special_flags[`DP_SP_INVALID] = special_flags[`DP_SP_INVALID] |
      (special_flags[`DP_SP_POS_INF] & special_flags[`DP_SP_NEG_INF]);
    merge_special = special_flags;
  end
endfunction
function automatic [`DP_SPECIAL_W-1:0] product_special(input [`DP_NUM_W-1:0] operand_a,
                                                       input [`DP_NUM_W-1:0] operand_b);
  reg [`DP_SPECIAL_W-1:0] special_flags;
  reg inf_value;
  reg zero_value;
  begin
    special_flags = 0;
    special_flags[`DP_SP_NAN] = (operand_a[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_NAN) |
      (operand_b[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_NAN);
    inf_value = (operand_a[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_INF) |
      (operand_b[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_INF);
    zero_value = (operand_a[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_ZERO) |
      (operand_b[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] == `DP_CLASS_ZERO);
    special_flags[`DP_SP_INVALID] = operand_a[`DP_NUM_SIGNAL] | operand_b[`DP_NUM_SIGNAL] |
      (inf_value & zero_value);
    if (inf_value & ~zero_value & ~special_flags[`DP_SP_NAN]) begin
      special_flags[`DP_SP_NEG_INF] = operand_a[`DP_NUM_SIGN] ^ operand_b[`DP_NUM_SIGN];
      special_flags[`DP_SP_POS_INF] = ~special_flags[`DP_SP_NEG_INF];
    end
    product_special = special_flags;
  end
endfunction
function automatic integer elements(input [`DP_TYPE_W-1:0] datatype);
  begin
    case (datatype)
      `DP_DT_TF32: elements = 1;
      `DP_DT_FP16, `DP_DT_BF16: elements = 2;
      `DP_DT_MXFP4, `DP_DT_NVFP4, `DP_DT_HIF4: elements = `DP_E_LANES;
      default: elements = `DP_Q_LANES;
    endcase
  end
endfunction
function automatic [`DP_SCALE_TYPE_W-1:0] scale_type(input [`DP_TYPE_W-1:0] datatype);
  begin
    case (datatype)
      `DP_DT_MX8_E4M3, `DP_DT_MX8_E5M2, `DP_DT_MX6_E3M2, `DP_DT_MX6_E2M3, `DP_DT_MXFP4:
      scale_type = `DP_SC_E8M0;
      `DP_DT_NVFP4: scale_type = `DP_SC_E4M3;
      `DP_DT_HIF4: scale_type = `DP_SC_E6M2;
      default: scale_type = `DP_SC_NONE;
    endcase
  end
endfunction
function automatic integer element_bias(input [`DP_TYPE_W-1:0] datatype);
  begin
    case (datatype)
      `DP_DT_TF32, `DP_DT_BF16: element_bias = `DP_FP32_BIAS;
      `DP_DT_FP16, `DP_DT_MX8_E4M3, `DP_DT_MX8_E5M2, `DP_DT_MX6_E3M2, `DP_DT_MX6_E2M3:
      element_bias = `DP_Q_BIAS;
      default: element_bias = 0;
    endcase
  end
endfunction
function automatic integer product_fraction(input [`DP_TYPE_W-1:0] datatype);
  begin
    case (datatype)
      `DP_DT_TF32, `DP_DT_FP16: product_fraction = 2 * `DP_FP16_F;
      `DP_DT_BF16: product_fraction = 2 * `DP_BF16_F;
      `DP_DT_HIF4: product_fraction = 2 * `DP_HIF_ELEMENT_F;
      `DP_DT_MXFP4, `DP_DT_NVFP4: product_fraction = 2 * `DP_E_ELEMENT_F;
      `DP_DT_INT8: product_fraction = 0;
      default: product_fraction = 2 * `DP_SCALE_F;
    endcase
  end
endfunction
function automatic integer lane_fraction(input [`DP_TYPE_W-1:0] datatype,
                                         input integer local_width);
  integer lane_width;
  begin
    lane_width = local_width + 1 + $clog2(`DP_Q_LANES);
    if (datatype == `DP_DT_INT8)
      lane_fraction = lane_width - `DP_INT_PRODUCT_W - $clog2(`DP_Q_LANES);
    else if (elements(datatype) == `DP_E_LANES)
      lane_fraction = product_fraction(
        datatype
      ) + `DP_E_GUARD + lane_width - (`DP_E_PAIR_W + `DP_E_GUARD + $clog2(
        `DP_E_LANES / 2
      ));
    // Datatype is a runtime input: DC requires constant $clog2 operands.
    // These arms equal log2(elements(t)) for all 16 datatype encodings;
    // E and INT8 have already taken their dedicated branches above.
    else
      case (datatype)
        `DP_DT_TF32: lane_fraction = local_width - 2 + $clog2(`DP_Q_LANES);
        `DP_DT_FP16, `DP_DT_BF16: lane_fraction = local_width - 2 + $clog2(`DP_Q_LANES) - 1;
        default: lane_fraction = local_width - 2;
      endcase
  end
endfunction
function automatic integer group_fraction(input [`DP_TYPE_W-1:0] datatype,
                                          input integer local_width);
  integer fractional_bits;
  begin
    fractional_bits = lane_fraction(datatype, local_width);
    if (datatype == `DP_DT_NVFP4 | datatype == `DP_DT_HIF4)
      group_fraction = fractional_bits + 2 * `DP_SCALE_F - 2 * `DP_SCALE_M;
    else group_fraction = fractional_bits;
  end
endfunction
function automatic integer anchor_width(input integer magnitude_width);
  begin
    // Includes raw anchor, post-LZD minimum and final normalization growth.
    anchor_width = 1 +
      $clog2(((-`DP_MIN_RAW_ANCHOR + magnitude_width - 1) > `DP_MAX_RAW_ANCHOR ?
              (-`DP_MIN_RAW_ANCHOR + magnitude_width - 1) : `DP_MAX_RAW_ANCHOR) + 1);
  end
endfunction
