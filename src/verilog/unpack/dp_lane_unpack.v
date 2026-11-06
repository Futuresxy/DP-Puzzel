`include "dp_defs.vh"
// S1 operand decoder and fixed-layout registers for one T1H2Q4E8 lane.
// Two atoms each use M16/E10/S4, plus class/signaling sidebands. Different
// formats share the same physical fields; widened element views are wires only.
// Synchronous enable, no reset on payload; caller's valid masks all bubbles.
// Each packed M field carries the unsigned magnitude from dp_operand_unpack.
// Its F follows datatype; E/M/S slots may include inactive fields.
module dp_lane_unpack (
  input wire clock,
  input wire rst_n,
  input wire in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [`DP_TYPE_W-1:0] in_registered_datatype,
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [1:0] in_e1,
  input wire in_e2,
  output wire [`DP_E_LANES*`DP_NUM_W-1:0] out_numbers
);
  // [S1 固定布局] 每侧两个 atom，每 atom 复用 M16/E10/S4；class/signaling 另存。
  // 先按当前 datatype 打包到容器，再由 DFF 保存；读端按已寄存 datatype 展开。
  // 不能用当前 in_datatype 解读旧寄存器，否则连续换型会造成字段错位。
  localparam integer ATOM_E = 2 * `DP_Q_EXP_W;
  localparam integer ATOM_S = `DP_E_LANES / `DP_LANES;
  wire [`DP_E_LANES*`DP_NUM_W-1:0] decoded;
  wire [`DP_HALF_W-1:0] mantissa_q[0:`DP_LANES-1];
  wire [ATOM_E-1:0] exponent_q[0:`DP_LANES-1];
  wire [ATOM_S-1:0] signs_q[0:`DP_LANES-1];
  wire [ATOM_S-1:0] signaling_q[0:`DP_LANES-1];
  wire [ATOM_S*`DP_NUM_CLASS_W-1:0] classes_q[0:`DP_LANES-1];
  genvar atom_index;
  genvar element_index;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_decode
      dp_operand_unpack #(
        .INDEX(element_index)
      ) u_decoder (
        .in_data(in_data),
        .in_datatype(in_datatype),
        .in_e1(in_e1),
        .in_e2(in_e2),
        .out_number(decoded[element_index*`DP_NUM_W+:`DP_NUM_W])
      );
    end
  endgenerate
  generate
    for (atom_index = 0; atom_index < `DP_LANES; atom_index = atom_index + 1) begin : g_atom
      wire [`DP_NUM_W-1:0] h_value;
      wire [2*`DP_NUM_W-1:0] q_values;
      wire [ATOM_S*`DP_NUM_W-1:0] e_values;
      wire [`DP_HALF_W-1:0] mantissa_d;
      wire [ATOM_E-1:0] exponent_d;
      wire [ATOM_S-1:0] signs_d;
      wire [ATOM_S-1:0] signaling_d;
      wire [ATOM_S*`DP_NUM_CLASS_W-1:0] classes_d;
      wire select_h;
      wire select_e;
      wire [`DP_HALF_W-1:0] h_mantissa;
      wire [`DP_HALF_W-1:0] e_mantissa;
      wire [`DP_HALF_W-1:0] q_mantissa;
      wire [ATOM_E-1:0] q_exponent;
      wire [ATOM_S-1:0] e_signs;
      wire [ATOM_S-1:0] q_signs;
      wire [ATOM_S-1:0] e_signaling;
      wire [ATOM_S-1:0] q_signaling;
      wire [ATOM_S*`DP_NUM_CLASS_W-1:0] e_classes;
      wire [ATOM_S*`DP_NUM_CLASS_W-1:0] q_classes;
      assign h_value = decoded[atom_index*`DP_NUM_W+:`DP_NUM_W];
      assign q_values = decoded[(atom_index*2)*`DP_NUM_W+:2*`DP_NUM_W];
      assign e_values = decoded[(atom_index*ATOM_S)*`DP_NUM_W+:ATOM_S*`DP_NUM_W];
      assign select_h = (in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) |
        (in_datatype == `DP_DT_BF16);
      assign select_e = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) |
        (in_datatype == `DP_DT_HIF4);
      assign h_mantissa = ((in_datatype != `DP_DT_TF32) | (atom_index == 0)) ?
        {{(`DP_HALF_W - `DP_MANT_W) {1'b0}}, h_value[`DP_NUM_MAG_LO+:`DP_MANT_W]} : 0;
      for (
        element_index = 0; element_index < ATOM_S; element_index = element_index + 1
      ) begin : g_pack_slot
        assign e_mantissa[element_index*`DP_MUL_LO+:`DP_MUL_LO] =
          e_values[element_index*`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_MUL_LO];
        assign e_signs[element_index] = e_values[element_index*`DP_NUM_W+`DP_NUM_SIGN];
        assign e_signaling[element_index] = e_values[element_index*`DP_NUM_W+`DP_NUM_SIGNAL];
        assign e_classes[element_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
          e_values[element_index*`DP_NUM_W+`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W];
        if (element_index < 2) begin : g_q_slot
          assign q_signs[element_index] = q_values[element_index*`DP_NUM_W+`DP_NUM_SIGN];
          assign q_signaling[element_index] = q_values[element_index*`DP_NUM_W+`DP_NUM_SIGNAL];
          assign q_classes[element_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
            q_values[element_index*`DP_NUM_W+`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W];
          assign q_exponent[element_index*`DP_Q_EXP_W+:`DP_Q_EXP_W] = in_datatype == `DP_DT_INT8 ?
            0 : q_values[element_index*`DP_NUM_W+`DP_NUM_EXP_LO+:`DP_Q_EXP_W];
        end else begin : g_unused_q
          assign q_signs[element_index] = 0;
          assign q_signaling[element_index] = 0;
          assign q_classes[element_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] = 0;
        end
      end
      assign q_mantissa = in_datatype == `DP_DT_INT8 ?
        {q_values[`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_QUARTER_W], q_values[`DP_NUM_MAG_LO+:`DP_QUARTER_W]}
        : {{(`DP_HALF_W - 2 * `DP_MUL_LO) {1'b0}}, q_values[`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_MUL_LO],
           q_values[`DP_NUM_MAG_LO+:`DP_MUL_LO]};
      assign mantissa_d = select_h ? h_mantissa : select_e ? e_mantissa : q_mantissa;
      assign exponent_d = select_h ?
        (((in_datatype != `DP_DT_TF32) | (atom_index == 0)) ?
         {{(ATOM_E - `DP_EXP_W) {1'b0}}, h_value[`DP_NUM_EXP_LO+:`DP_EXP_W]} : 0) :
        select_e ? {{(ATOM_E - 1) {1'b0}}, e_values[`DP_NUM_EXP_LO]} : q_exponent;
      assign signs_d = select_h ? (((in_datatype != `DP_DT_TF32) | (atom_index == 0)) ?
                                   {{(ATOM_S - 1) {1'b0}}, h_value[`DP_NUM_SIGN]} : 0) :
        select_e ? e_signs : q_signs;
      assign signaling_d = select_h ? (((in_datatype != `DP_DT_TF32) | (atom_index == 0)) ?
                                       {{(ATOM_S - 1) {1'b0}}, h_value[`DP_NUM_SIGNAL]} : 0) :
        select_e ? e_signaling : q_signaling;
      assign classes_d = select_h ?
        (((in_datatype != `DP_DT_TF32) | (atom_index == 0)) ?
         {{((ATOM_S - 1) * `DP_NUM_CLASS_W) {1'b0}}, h_value[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W]} :
         0) : select_e ? e_classes : q_classes;

      // S0 -> S1: mantissa_q_atom.
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_HALF_W))
      ff_s0_s1_mantissa_q_atom (.clock(clock), .in_en(rst_n & in_valid), .in_d(mantissa_d), .out_q(mantissa_q[atom_index]));
      // S0 -> S1: exponent_q_atom.
      dp_lib_DFFE #(.WIDTH(ATOM_E))
      ff_s0_s1_exponent_q_atom (.clock(clock), .in_en(rst_n & in_valid), .in_d(exponent_d), .out_q(exponent_q[atom_index]));
      // S0 -> S1: signs_q_atom.
      dp_lib_DFFE #(.WIDTH(ATOM_S))
      ff_s0_s1_signs_q_atom (.clock(clock), .in_en(rst_n & in_valid), .in_d(signs_d), .out_q(signs_q[atom_index]));
      // S0 -> S1: classes_q_atom.
      dp_lib_DFFE #(.WIDTH(ATOM_S * `DP_NUM_CLASS_W))
      ff_s0_s1_classes_q_atom (.clock(clock), .in_en(rst_n & in_valid), .in_d(classes_d), .out_q(classes_q[atom_index]));
      // S0 -> S1: signaling_q_atom.
      dp_lib_DFFE #(.WIDTH(ATOM_S))
      ff_s0_s1_signaling_q_atom (.clock(clock), .in_en(rst_n & in_valid), .in_d(signaling_d), .out_q(signaling_q[atom_index]));
      // verilog_format: on

    end
  endgenerate
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_expand
      // S1 出口展开只增加连线视图，不为各格式复制寄存器。
      wire [`DP_NUM_W-1:0] h_number;
      wire [`DP_NUM_W-1:0] q_number;
      wire [`DP_NUM_W-1:0] e_number;
      wire select_h;
      wire select_e;
      assign select_h = (in_registered_datatype == `DP_DT_TF32) |
        (in_registered_datatype == `DP_DT_FP16) | (in_registered_datatype == `DP_DT_BF16);
      assign select_e = (in_registered_datatype == `DP_DT_MXFP4) |
        (in_registered_datatype == `DP_DT_NVFP4) | (in_registered_datatype == `DP_DT_HIF4);
      assign
        h_number[`DP_NUM_MAG_LO+:`DP_MANT_W] = mantissa_q[element_index%`DP_LANES][0+:`DP_MANT_W];
      assign
        h_number[`DP_NUM_EXP_LO+:`DP_EXP_W] = exponent_q[element_index%`DP_LANES][0+:`DP_EXP_W];
      assign h_number[`DP_NUM_SIGN] = signs_q[element_index%`DP_LANES][0];
      assign h_number[`DP_NUM_SIGNAL] = signaling_q[element_index%`DP_LANES][0];
      assign h_number[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
        classes_q[element_index%`DP_LANES][0+:`DP_NUM_CLASS_W];
      assign e_number[`DP_NUM_MAG_LO+:`DP_MANT_W] = {
        {(`DP_MANT_W - `DP_MUL_LO) {1'b0}},
        mantissa_q[element_index/ATOM_S][(element_index%ATOM_S)*`DP_MUL_LO+:`DP_MUL_LO]
      };
      assign e_number[`DP_NUM_EXP_LO+:`DP_EXP_W] = {
        {(`DP_EXP_W - 1) {1'b0}}, exponent_q[element_index/ATOM_S][0]
      };
      assign e_number[`DP_NUM_SIGN] = signs_q[element_index/ATOM_S][element_index%ATOM_S];
      assign e_number[`DP_NUM_SIGNAL] = signaling_q[element_index/ATOM_S][element_index%ATOM_S];
      assign e_number[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
        classes_q[element_index/ATOM_S][(element_index%ATOM_S)*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
      assign q_number[`DP_NUM_MAG_LO+:`DP_MANT_W] = in_registered_datatype == `DP_DT_INT8 ?
        {{(`DP_MANT_W - `DP_QUARTER_W) {1'b0}},
         mantissa_q[(element_index/2)%`DP_LANES][(element_index%2)*`DP_QUARTER_W+:`DP_QUARTER_W]} :
        {{(`DP_MANT_W - `DP_MUL_LO) {1'b0}},
         mantissa_q[(element_index/2)%`DP_LANES][(element_index%2)*`DP_MUL_LO+:`DP_MUL_LO]};
      assign q_number[`DP_NUM_EXP_LO+:`DP_EXP_W] = in_registered_datatype == `DP_DT_INT8 ?
        0 : {{(`DP_EXP_W - `DP_Q_EXP_W) {1'b0}},
             exponent_q[(element_index/2)%`DP_LANES][(element_index%2)*`DP_Q_EXP_W+:`DP_Q_EXP_W]};
      assign q_number[`DP_NUM_SIGN] = signs_q[(element_index/2)%`DP_LANES][element_index%2];
      assign q_number[`DP_NUM_SIGNAL] = signaling_q[(element_index/2)%`DP_LANES][element_index%2];
      assign q_number[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
        classes_q[(element_index/2)%`DP_LANES][(element_index%2)*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
      assign out_numbers[element_index*`DP_NUM_W+:`DP_NUM_W] = select_h ?
        (((element_index < `DP_LANES) &
          ((in_registered_datatype != `DP_DT_TF32) | (element_index == 0))) ? h_number : 0) :
        select_e ? e_number : element_index < `DP_Q_LANES ? q_number : 0;
    end
  endgenerate
endmodule
