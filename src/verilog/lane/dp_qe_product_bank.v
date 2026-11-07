`include "dp_defs.vh"
// S2 combinational Q4/E8 bank. Exactly eight unsigned 4x4 multipliers;
// Q activates four slots, E activates eight. No T/H/INT8 arithmetic.
// Precision | operand S I F | product S I F
// Q         | 0 1 3         | 0 2 6
// MX/NV     | 0 3 1         | 0 6 2
// HiF4      | 0 2 2         | 0 4 4
// Sign/class travel through unpack's independent sideband. Exponent sums U6.
module dp_qe_product_bank (
  // Registered S1 format and valid isolate inactive multiplier inputs.
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire in_enable,
  // Compact two-atom M32 and E20 buses, with format-defined field slices.
  input wire [`DP_UNPACK_MANT_W-1:0] in_a_mantissas,
  input wire [`DP_UNPACK_MANT_W-1:0] in_b_mantissas,
  input wire [`DP_UNPACK_EXP_W-1:0] in_a_exponents,
  input wire [`DP_UNPACK_EXP_W-1:0] in_b_exponents,
  // Logical slots Q0..3 or E0..7, each natural W8 product and U6 exponent sum.
  output wire [`DP_E_LANES*2*`DP_EIGHTH_W-1:0] out_products,
  output wire [`DP_E_LANES*(`DP_Q_EXP_W+1)-1:0] out_exponents
);
  // E mode selects four nibbles per atom; Q selects its two low nibbles.
  wire select_e;
  assign select_e = (in_datatype >= `DP_DT_MXFP4) & (in_datatype <= `DP_DT_HIF4);
  // Static physical multiplier slot; no runtime array indexing.
  genvar element_index;
  generate
    for (element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1) begin : g_product
      // Q's slot mapping is capped for unused E-only slots to avoid invalid slices.
      localparam integer Q_INDEX = element_index % `DP_Q_LANES;
      localparam integer Q_MANT_OFFSET = (Q_INDEX/`DP_UNPACK_ATOM_Q_LANES)*`DP_HALF_W +
                                         (Q_INDEX%`DP_UNPACK_ATOM_Q_LANES)*`DP_EIGHTH_W;
      localparam integer Q_EXP_OFFSET = (Q_INDEX/`DP_UNPACK_ATOM_Q_LANES)*`DP_UNPACK_ATOM_EXP_W +
                                        (Q_INDEX%`DP_UNPACK_ATOM_Q_LANES)*`DP_Q_EXP_W;
      // Operand isolation includes invalid cycles and Q's four unused slots.
      wire slot_enabled;
      wire [`DP_EIGHTH_W-1:0] a_magnitude;
      wire [`DP_EIGHTH_W-1:0] b_magnitude;
      wire [`DP_Q_EXP_W-1:0] a_exponent;
      wire [`DP_Q_EXP_W-1:0] b_exponent;
      assign slot_enabled = in_enable & (select_e | (element_index < `DP_Q_LANES));
      assign a_magnitude = ~slot_enabled ? 0 : select_e ?
                           in_a_mantissas[element_index*`DP_EIGHTH_W+:`DP_EIGHTH_W] :
                           in_a_mantissas[Q_MANT_OFFSET+:`DP_EIGHTH_W];
      assign b_magnitude = ~slot_enabled ? 0 : select_e ?
                           in_b_mantissas[element_index*`DP_EIGHTH_W+:`DP_EIGHTH_W] :
                           in_b_mantissas[Q_MANT_OFFSET+:`DP_EIGHTH_W];
      assign a_exponent = ~slot_enabled ? 0 : select_e ?
                          {{(`DP_Q_EXP_W-1){1'b0}},in_a_exponents[0]} :
                          in_a_exponents[Q_EXP_OFFSET+:`DP_Q_EXP_W];
      assign b_exponent = ~slot_enabled ? 0 : select_e ?
                          {{(`DP_Q_EXP_W-1){1'b0}},in_b_exponents[0]} :
                          in_b_exponents[Q_EXP_OFFSET+:`DP_Q_EXP_W];
      dp_mul_unsigned #(
          .A_W(`DP_EIGHTH_W),
          .B_W(`DP_EIGHTH_W)
      ) u_mantissa_multiply (
          .in_a       (a_magnitude),
          .in_b       (b_magnitude),
          .out_product(out_products[element_index*2*`DP_EIGHTH_W+:2*`DP_EIGHTH_W])
      );
      assign out_exponents[element_index*(`DP_Q_EXP_W+1)+:`DP_Q_EXP_W+1] = {1'b0, a_exponent} + {1'b0, b_exponent};
    end
  endgenerate
endmodule
