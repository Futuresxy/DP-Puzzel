`include "dp_defs.vh"
// 固定格式直接生成一个 M16/E10/S4 atom；纯组合，无流水寄存器。
// FORMAT_INDEX、字段宽度和切片位置均为 elaboration 常量，不用运行时宽度/掩码。
// T/FP16: M=I1F10；BF16: I1F7；Q: 两个 I1F3；MX/NV: 四个 I3F1；HiF: 四个 I2F2。
// NaN/Inf 在原编码上分类，数值占位 M=0/E=1；负零、sNaN 独立保留。
module dp_unpack_atom #(
  // 单侧 32 位 lane 中的 atom 编号；TF32 仅 atom0 有效。
  parameter integer ATOM_INDEX = 0,
  // 静态能力开关；非零时移除 T/H/INT8 路径。
  parameter integer QE_ONLY = 0
) (
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [1:0] in_e1,
  input wire in_e2,
  output wire [`DP_HALF_W-1:0] out_mantissas,
  output wire [`DP_UNPACK_ATOM_EXP_W-1:0] out_exponents,
  output wire [`DP_UNPACK_ATOM_SIGN_W-1:0] out_signs,
  output wire [`DP_UNPACK_ATOM_CLASS_W-1:0] out_classes,
  output wire [`DP_UNPACK_ATOM_SIGN_W-1:0] out_signaling
);
  // datatype 连续编码的已支持格式数；仅用于生成固定格式候选。
  localparam integer FORMAT_COUNT = {28'd0, `DP_DT_INT8} + 1;
  // 每格式在规定 atom 布局中的组合候选，未使用位显式补零。
  wire [`DP_HALF_W-1:0] format_mantissas [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_EXP_W-1:0] format_exponents [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] format_signs [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_CLASS_W-1:0] format_classes [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] format_signaling [0:FORMAT_COUNT-1];
  // one-hot 格式选择后分别归约；无匹配格式时输出全零。
  wire [`DP_HALF_W-1:0] selected_mantissas [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_EXP_W-1:0] selected_exponents [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] selected_signs [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_CLASS_W-1:0] selected_classes [0:FORMAT_COUNT-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] selected_signaling [0:FORMAT_COUNT-1];
  // 生成期格式和元素槽索引。
  genvar format_index;
  genvar slot_index;

  generate
    for (format_index = 0; format_index < FORMAT_COUNT; format_index = format_index + 1) begin : g_format
      // 固定候选使能，不用于改变字段宽度或取位位置。
      wire format_selected;
      assign format_selected = in_datatype == format_index;
      if (((QE_ONLY != 0) & ((format_index <= `DP_DT_BF16) | (format_index == `DP_DT_INT8))) |
          ((ATOM_INDEX != 0) & (format_index == `DP_DT_TF32))) begin : g_unused
        assign format_mantissas[format_index] = 0;
        assign format_exponents[format_index] = 0;
        assign format_signs[format_index]     = 0;
        assign format_classes[format_index]   = 0;
        assign format_signaling[format_index] = 0;
      end else if (format_index <= `DP_DT_MX6_E2M3) begin : g_float
        // 以下 localparam 均是静态常量；H/T 每 atom 一项，Q 每 atom 两项。
        localparam IS_Q = format_index >= `DP_DT_MX8_E4M3;
        localparam integer SLOT_COUNT = IS_Q ? `DP_UNPACK_ATOM_Q_LANES : 1;
        // 原始 exponent/fraction 的位数，不是运行时信号。
        localparam integer EXP_FIELD_W = ((format_index == `DP_DT_TF32) | (format_index == `DP_DT_BF16)) ? `DP_FP32_E :
                                         ((format_index == `DP_DT_FP16) | (format_index == `DP_DT_MX8_E5M2)) ? `DP_FP16_E :
                                         (format_index == `DP_DT_MX8_E4M3) ? `DP_MX8_E4_E :
                                         (format_index == `DP_DT_MX6_E3M2) ? `DP_MX6_E3_E : `DP_MX6_E2_E;
        localparam integer FRACTION_W = ((format_index == `DP_DT_TF32) | (format_index == `DP_DT_FP16)) ? `DP_FP16_F :
                                        (format_index == `DP_DT_BF16) ? `DP_BF16_F :
                                        ((format_index == `DP_DT_MX8_E4M3) | (format_index == `DP_DT_MX6_E2M3)) ? `DP_MX8_E4_F : `DP_MX8_E5_F;
        // 内部 Q 统一 F3/bias15；T/H 保持原 fraction 和偏置。
        localparam integer MANTISSA_W = IS_Q ? `DP_MUL_LO : FRACTION_W + 1;
        localparam integer EXP_PACK_W = IS_Q ? `DP_Q_EXP_W : `DP_EXP_W;
        localparam [EXP_PACK_W-1:0] EXP_OFFSET = (format_index == `DP_DT_MX8_E4M3) ? `DP_Q_BIAS - `DP_MX8_E4_BIAS :
                                               (format_index == `DP_DT_MX6_E3M2) ? `DP_Q_BIAS - `DP_MX6_E3_BIAS :
                                               (format_index == `DP_DT_MX6_E2M3) ? `DP_Q_BIAS - `DP_MX6_E2_BIAS : 0;
        // IEEE 类有 Inf/sNaN；E4M3 仅末编码为 NaN，FP6 全部有限。
        localparam HAS_INF = (format_index <= `DP_DT_BF16) | (format_index == `DP_DT_MX8_E5M2);
        for (slot_index = 0; slot_index < SLOT_COUNT; slot_index = slot_index + 1) begin : g_slot
          // 固定切片：TF32 [31:13]，H 为半字，Q 为字节，FP6 去除低两位 padding。
          localparam integer RAW_LSB = (format_index == `DP_DT_TF32) ? `DP_TF32_PAD :
                                       IS_Q ? (ATOM_INDEX * `DP_UNPACK_ATOM_Q_LANES + slot_index) * `DP_QUARTER_W +
                                              ((format_index >= `DP_DT_MX6_E3M2) ? `DP_MX6_PAD : 0) : ATOM_INDEX * `DP_HALF_W;
          // 原始字段直接参与分类；零/非正规数 hidden bit 为零。
          wire [EXP_FIELD_W-1:0] exponent_field;
          wire [FRACTION_W-1:0] fraction_field;
          wire exponent_nonzero;
          wire exponent_all_ones;
          wire fraction_nonzero;
          wire number_nan;
          wire number_inf;
          wire number_zero;
          wire [EXP_PACK_W-1:0] effective_exponent;
          assign exponent_field     = in_data[RAW_LSB+FRACTION_W+:EXP_FIELD_W];
          assign fraction_field     = in_data[RAW_LSB+:FRACTION_W];
          assign exponent_nonzero   = |exponent_field;
          assign exponent_all_ones  = &exponent_field;
          assign fraction_nonzero   = |fraction_field;
          assign number_nan         = exponent_all_ones & ((HAS_INF & fraction_nonzero) |
                                      ((format_index == `DP_DT_MX8_E4M3) & (&fraction_field)));
          assign number_inf         = HAS_INF & exponent_all_ones & ~fraction_nonzero;
          assign number_zero        = ~exponent_nonzero & ~fraction_nonzero;
          assign effective_exponent = (exponent_nonzero ? {{(EXP_PACK_W-EXP_FIELD_W){1'b0}}, exponent_field} : {{(EXP_PACK_W-1){1'b0}}, 1'b1}) + EXP_OFFSET;
          // 直接写入当前格式的 M/E/S/class 槽；补零为连接，不产生数值移位器。
          assign format_mantissas[format_index][slot_index*MANTISSA_W+:MANTISSA_W] =
            (number_nan | number_inf) ? {MANTISSA_W{1'b0}} : {exponent_nonzero, fraction_field, {(MANTISSA_W-FRACTION_W-1){1'b0}}};
          assign format_exponents[format_index][slot_index*EXP_PACK_W+:EXP_PACK_W] =
            (number_nan | number_inf) ? {{(EXP_PACK_W-1){1'b0}}, 1'b1} : effective_exponent;
          assign format_signs[format_index][slot_index] = in_data[RAW_LSB+FRACTION_W+EXP_FIELD_W];
          assign format_classes[format_index][slot_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
            number_nan ? `DP_CLASS_NAN : number_inf ? `DP_CLASS_INF : number_zero ? `DP_CLASS_ZERO : `DP_CLASS_FINITE;
          assign format_signaling[format_index][slot_index] = number_nan & HAS_INF & ~fraction_field[FRACTION_W-1];
        end
        assign format_mantissas[format_index][`DP_HALF_W-1:SLOT_COUNT*MANTISSA_W] = 0;
        if (SLOT_COUNT * EXP_PACK_W < `DP_UNPACK_ATOM_EXP_W) begin : g_exp_pad
          assign format_exponents[format_index][`DP_UNPACK_ATOM_EXP_W-1:SLOT_COUNT*EXP_PACK_W] = 0;
        end
        assign format_signs[format_index][`DP_UNPACK_ATOM_SIGN_W-1:SLOT_COUNT] = 0;
        assign format_classes[format_index][`DP_UNPACK_ATOM_CLASS_W-1:SLOT_COUNT*`DP_NUM_CLASS_W] = 0;
        assign format_signaling[format_index][`DP_UNPACK_ATOM_SIGN_W-1:SLOT_COUNT] = 0;
      end else if (format_index <= `DP_DT_HIF4) begin : g_e
        // MX/NV 共用 E2M1 数值表；HiF4 仅一位 e1 控制两个固定拼接。
        for (slot_index = 0; slot_index < `DP_UNPACK_ATOM_SIGN_W; slot_index = slot_index + 1) begin : g_slot
          localparam integer RAW_LSB = (ATOM_INDEX * `DP_UNPACK_ATOM_SIGN_W + slot_index) * `DP_EIGHTH_W;
          wire [`DP_E_PAYLOAD_W-1:0] payload;
          wire [`DP_MUL_LO-1:0] magnitude;
          assign payload = in_data[RAW_LSB+:`DP_E_PAYLOAD_W];
          if (format_index == `DP_DT_HIF4) begin : g_hif
            assign magnitude = in_e1[ATOM_INDEX] ? {payload, 1'b0} : {1'b0, payload};
          end else begin : g_mx_nv
            assign magnitude = payload < 3'd5 ? {1'b0, payload} :
                               payload == 3'd5 ? 4'd6 : payload == 3'd6 ? 4'd8 : 4'd12;
          end
          assign format_mantissas[format_index][slot_index*`DP_MUL_LO+:`DP_MUL_LO] = magnitude;
          assign format_signs[format_index][slot_index] = in_data[RAW_LSB+`DP_E_PAYLOAD_W];
          assign format_classes[format_index][slot_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
            (|payload) ? `DP_CLASS_FINITE : `DP_CLASS_ZERO;
        end
        assign format_exponents[format_index] = (format_index == `DP_DT_HIF4) ? {{(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, in_e2} : 0;
        assign format_signaling[format_index] = 0;
      end else begin : g_int
        // 两个 INT8 coefficient，保留 abs(-128)=128；后续仍按既定整数路径计算。
        for (slot_index = 0; slot_index < `DP_UNPACK_ATOM_Q_LANES; slot_index = slot_index + 1) begin : g_slot
          localparam integer RAW_LSB = (ATOM_INDEX * `DP_UNPACK_ATOM_Q_LANES + slot_index) * `DP_QUARTER_W;
          wire [`DP_QUARTER_W-1:0] raw_integer;
          assign raw_integer = in_data[RAW_LSB+:`DP_QUARTER_W];
          assign format_mantissas[format_index][slot_index*`DP_QUARTER_W+:`DP_QUARTER_W] =
            raw_integer[`DP_QUARTER_W-1] ? (~raw_integer + {{(`DP_QUARTER_W-1){1'b0}}, 1'b1}) : raw_integer;
          assign format_signs[format_index][slot_index] = raw_integer[`DP_QUARTER_W-1];
          assign format_classes[format_index][slot_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
            (|raw_integer) ? `DP_CLASS_FINITE : `DP_CLASS_ZERO;
        end
        assign format_exponents[format_index] = 0;
        assign format_signs[format_index][`DP_UNPACK_ATOM_SIGN_W-1:`DP_UNPACK_ATOM_Q_LANES] = 0;
        assign format_classes[format_index][`DP_UNPACK_ATOM_CLASS_W-1:`DP_UNPACK_ATOM_Q_LANES*`DP_NUM_CLASS_W] = 0;
        assign format_signaling[format_index] = 0;
      end
      // 互斥格式的 AND/OR 选择，综合可平衡；不形成有优先级的格式选择链。
      assign selected_mantissas[format_index] = ({`DP_HALF_W{format_selected}} & format_mantissas[format_index]);
      assign selected_exponents[format_index] = ({`DP_UNPACK_ATOM_EXP_W{format_selected}} & format_exponents[format_index]);
      assign selected_signs[format_index]     = ({`DP_UNPACK_ATOM_SIGN_W{format_selected}} & format_signs[format_index]);
      assign selected_classes[format_index]   = ({`DP_UNPACK_ATOM_CLASS_W{format_selected}} & format_classes[format_index]);
      assign selected_signaling[format_index] = ({`DP_UNPACK_ATOM_SIGN_W{format_selected}} & format_signaling[format_index]);
    end
  endgenerate
  assign out_mantissas =
    selected_mantissas[`DP_DT_TF32] |
    selected_mantissas[`DP_DT_FP16] |
    selected_mantissas[`DP_DT_BF16] |
    selected_mantissas[`DP_DT_MX8_E4M3] |
    selected_mantissas[`DP_DT_MX8_E5M2] |
    selected_mantissas[`DP_DT_MX6_E3M2] |
    selected_mantissas[`DP_DT_MX6_E2M3] |
    selected_mantissas[`DP_DT_MXFP4] |
    selected_mantissas[`DP_DT_NVFP4] |
    selected_mantissas[`DP_DT_HIF4] |
    selected_mantissas[`DP_DT_INT8];
  assign out_exponents =
    selected_exponents[`DP_DT_TF32] |
    selected_exponents[`DP_DT_FP16] |
    selected_exponents[`DP_DT_BF16] |
    selected_exponents[`DP_DT_MX8_E4M3] |
    selected_exponents[`DP_DT_MX8_E5M2] |
    selected_exponents[`DP_DT_MX6_E3M2] |
    selected_exponents[`DP_DT_MX6_E2M3] |
    selected_exponents[`DP_DT_MXFP4] |
    selected_exponents[`DP_DT_NVFP4] |
    selected_exponents[`DP_DT_HIF4] |
    selected_exponents[`DP_DT_INT8];
  assign out_signs =
    selected_signs[`DP_DT_TF32] |
    selected_signs[`DP_DT_FP16] |
    selected_signs[`DP_DT_BF16] |
    selected_signs[`DP_DT_MX8_E4M3] |
    selected_signs[`DP_DT_MX8_E5M2] |
    selected_signs[`DP_DT_MX6_E3M2] |
    selected_signs[`DP_DT_MX6_E2M3] |
    selected_signs[`DP_DT_MXFP4] |
    selected_signs[`DP_DT_NVFP4] |
    selected_signs[`DP_DT_HIF4] |
    selected_signs[`DP_DT_INT8];
  assign out_classes =
    selected_classes[`DP_DT_TF32] |
    selected_classes[`DP_DT_FP16] |
    selected_classes[`DP_DT_BF16] |
    selected_classes[`DP_DT_MX8_E4M3] |
    selected_classes[`DP_DT_MX8_E5M2] |
    selected_classes[`DP_DT_MX6_E3M2] |
    selected_classes[`DP_DT_MX6_E2M3] |
    selected_classes[`DP_DT_MXFP4] |
    selected_classes[`DP_DT_NVFP4] |
    selected_classes[`DP_DT_HIF4] |
    selected_classes[`DP_DT_INT8];
  assign out_signaling =
    selected_signaling[`DP_DT_TF32] |
    selected_signaling[`DP_DT_FP16] |
    selected_signaling[`DP_DT_BF16] |
    selected_signaling[`DP_DT_MX8_E4M3] |
    selected_signaling[`DP_DT_MX8_E5M2] |
    selected_signaling[`DP_DT_MX6_E3M2] |
    selected_signaling[`DP_DT_MX6_E2M3] |
    selected_signaling[`DP_DT_MXFP4] |
    selected_signaling[`DP_DT_NVFP4] |
    selected_signaling[`DP_DT_HIF4] |
    selected_signaling[`DP_DT_INT8];
endmodule
