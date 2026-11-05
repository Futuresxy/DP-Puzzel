`include "dp_defs.vh"
// S1 operand decoder and fixed-layout registers for one T1H2Q4E8 lane.
// Two atoms each use M16/E10/S4, plus class/signaling sidebands. Different
// formats share the same physical fields; widened element views are wires only.
// Synchronous enable, no reset on payload; caller's valid masks all bubbles.
// Each packed M field carries the unsigned magnitude from dp_operand_unpack.
// Its F follows datatype; E/M/S slots may include inactive fields.
module dp_lane_unpack (
  // verilog_format: off  // Keep ports sharing one declaration on the same line.
  input wire clock,reset,in_valid,
  input wire [`DP_TYPE_W-1:0] in_datatype,in_registered_datatype,
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [1:0] in_e1,
  input wire in_e2,
  output wire [`DP_E_LANES*`DP_NUM_W-1:0] out_numbers
  // verilog_format: on
);
  localparam integer ATOMS = `DP_LANES,
    ATOM_M = `DP_HALF_W, ATOM_E = 2 * `DP_Q_EXP_W, ATOM_S = `DP_E_LANES / ATOMS;
  wire [`DP_E_LANES*`DP_NUM_W-1:0] decoded;
  reg [ATOM_M-1:0] mantissa_q[0:ATOMS-1];
  reg [ATOM_E-1:0] exponent_q[0:ATOMS-1];
  reg [ATOM_S-1:0] signs_q[0:ATOMS-1], signaling_q[0:ATOMS-1];
  reg [ATOM_S*`DP_NUM_CLASS_W-1:0] classes_q[0:ATOMS-1];
  genvar atom, j;
  generate
    for (j = 0; j < `DP_E_LANES; j = j + 1) begin : g_decode
      dp_operand_unpack #(
        .INDEX(j)
      ) decoder (
        .in_data(in_data),
        .in_datatype(in_datatype),
        .in_e1(in_e1),
        .in_e2(in_e2),
        .out_number(decoded[j*`DP_NUM_W+:`DP_NUM_W])
      );
    end
  endgenerate
  generate
    for (atom = 0; atom < ATOMS; atom = atom + 1) begin : g_atom
      wire [`DP_NUM_W-1:0] h_value;
      wire [2*`DP_NUM_W-1:0] q_values;
      wire [ATOM_S*`DP_NUM_W-1:0] e_values;
      reg [ATOM_M-1:0] mantissa_d;
      reg [ATOM_E-1:0] exponent_d;
      reg [ATOM_S-1:0] signs_d, signaling_d;
      reg [ATOM_S*`DP_NUM_CLASS_W-1:0] classes_d;
      integer slot;
      assign h_value  = decoded[atom*`DP_NUM_W+:`DP_NUM_W];
      assign q_values = decoded[(atom*2)*`DP_NUM_W+:2*`DP_NUM_W];
      assign e_values = decoded[(atom*ATOM_S)*`DP_NUM_W+:ATOM_S*`DP_NUM_W];
      always @* begin
        mantissa_d = 0;
        exponent_d = 0;
        signs_d = 0;
        classes_d = 0;
        signaling_d = 0;
        case (in_datatype)
          `DP_DT_TF32, `DP_DT_FP16, `DP_DT_BF16:
          if (in_datatype != `DP_DT_TF32 || atom == 0) begin
            mantissa_d[0+:`DP_MANT_W] = h_value[`DP_NUM_MAG_LO+:`DP_MANT_W];
            exponent_d[0+:`DP_EXP_W] = h_value[`DP_NUM_EXP_LO+:`DP_EXP_W];
            signs_d[0] = h_value[`DP_NUM_SIGN];
            classes_d[0+:`DP_NUM_CLASS_W] = h_value[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W];
            signaling_d[0] = h_value[`DP_NUM_SIGNAL];
          end
          `DP_DT_MXFP4, `DP_DT_NVFP4, `DP_DT_HIF4: begin
            exponent_d[0] = e_values[`DP_NUM_EXP_LO];
            for (slot = 0; slot < ATOM_S; slot = slot + 1) begin
              mantissa_d[slot*`DP_MUL_LO+:`DP_MUL_LO] =
                e_values[slot*`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_MUL_LO];
              signs_d[slot] = e_values[slot*`DP_NUM_W+`DP_NUM_SIGN];
              classes_d[slot*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
                e_values[slot*`DP_NUM_W+`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W];
              signaling_d[slot] = e_values[slot*`DP_NUM_W+`DP_NUM_SIGNAL];
            end
          end
          default:
          for (slot = 0; slot < 2; slot = slot + 1) begin
            if (in_datatype == `DP_DT_INT8)
              mantissa_d[slot*`DP_QUARTER_W+:`DP_QUARTER_W] =
                q_values[slot*`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_QUARTER_W];
            else begin
              mantissa_d[slot*`DP_MUL_LO+:`DP_MUL_LO] =
                q_values[slot*`DP_NUM_W+`DP_NUM_MAG_LO+:`DP_MUL_LO];
              exponent_d[slot*`DP_Q_EXP_W+:`DP_Q_EXP_W] =
                q_values[slot*`DP_NUM_W+`DP_NUM_EXP_LO+:`DP_Q_EXP_W];
            end
            signs_d[slot] = q_values[slot*`DP_NUM_W+`DP_NUM_SIGN];
            classes_d[slot*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] =
              q_values[slot*`DP_NUM_W+`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W];
            signaling_d[slot] = q_values[slot*`DP_NUM_W+`DP_NUM_SIGNAL];
          end
        endcase
      end
      always @(posedge clock)
        if (!reset && in_valid) begin
          mantissa_q[atom] <= mantissa_d;
          exponent_q[atom] <= exponent_d;
          signs_q[atom] <= signs_d;
          classes_q[atom] <= classes_d;
          signaling_q[atom] <= signaling_d;
        end
    end
  endgenerate
  generate
    for (j = 0; j < `DP_E_LANES; j = j + 1) begin : g_expand
      reg [`DP_NUM_W-1:0] number_value;
      always @* begin
        number_value = 0;
        case (in_registered_datatype)
          `DP_DT_TF32, `DP_DT_FP16, `DP_DT_BF16: begin
            if (j < ATOMS && (in_registered_datatype != `DP_DT_TF32 || j == 0)) begin
              number_value[`DP_NUM_MAG_LO+:`DP_MANT_W] = mantissa_q[j%ATOMS][0+:`DP_MANT_W];
              number_value[`DP_NUM_EXP_LO+:`DP_EXP_W] = exponent_q[j%ATOMS][0+:`DP_EXP_W];
              number_value[`DP_NUM_SIGN] = signs_q[j%ATOMS][0];
              number_value[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
                classes_q[j%ATOMS][0+:`DP_NUM_CLASS_W];
              number_value[`DP_NUM_SIGNAL] = signaling_q[j%ATOMS][0];
            end
          end
          `DP_DT_MXFP4, `DP_DT_NVFP4, `DP_DT_HIF4: begin
            number_value[`DP_NUM_MAG_LO+:`DP_MUL_LO] =
              mantissa_q[j/ATOM_S][(j%ATOM_S)*`DP_MUL_LO+:`DP_MUL_LO];
            number_value[`DP_NUM_EXP_LO] = exponent_q[j/ATOM_S][0];
            number_value[`DP_NUM_SIGN] = signs_q[j/ATOM_S][j%ATOM_S];
            number_value[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
              classes_q[j/ATOM_S][(j%ATOM_S)*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
            number_value[`DP_NUM_SIGNAL] = signaling_q[j/ATOM_S][j%ATOM_S];
          end
          default:
          if (j < `DP_Q_LANES) begin
            if (in_registered_datatype == `DP_DT_INT8)
              number_value[`DP_NUM_MAG_LO+:`DP_QUARTER_W] =
                mantissa_q[(j/2)%ATOMS][(j%2)*`DP_QUARTER_W+:`DP_QUARTER_W];
            else begin
              number_value[`DP_NUM_MAG_LO+:`DP_MUL_LO] =
                mantissa_q[(j/2)%ATOMS][(j%2)*`DP_MUL_LO+:`DP_MUL_LO];
              number_value[`DP_NUM_EXP_LO+:`DP_Q_EXP_W] =
                exponent_q[(j/2)%ATOMS][(j%2)*`DP_Q_EXP_W+:`DP_Q_EXP_W];
            end
            number_value[`DP_NUM_SIGN] = signs_q[(j/2)%ATOMS][j%2];
            number_value[`DP_NUM_CLASS_LO+:`DP_NUM_CLASS_W] =
              classes_q[(j/2)%ATOMS][(j%2)*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W];
            number_value[`DP_NUM_SIGNAL] = signaling_q[(j/2)%ATOMS][j%2];
          end
        endcase
      end
      assign out_numbers[j*`DP_NUM_W+:`DP_NUM_W] = number_value;
    end
  endgenerate
endmodule
