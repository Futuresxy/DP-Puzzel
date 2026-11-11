// Hierarchy aliases for maintained Verilog and frozen SV replay.
`ifdef DP_LEGACY_SV
`define DP_TRACE_GROUP_UNIT group_unit
`define DP_TRACE_LANE lane
`define DP_TRACE_OPERAND_UNPACK_A operand_unpack_a
`define DP_TRACE_OPERAND_UNPACK_B operand_unpack_b
`else
`define DP_TRACE_GROUP_UNIT u_group_unit
`define DP_TRACE_LANE u_lane
`define DP_TRACE_OPERAND_UNPACK_A u_lane_unpack.u_operand_a
`define DP_TRACE_OPERAND_UNPACK_B u_lane_unpack.u_operand_b
`endif

`ifdef DP_LEGACY_SV
`define DP_TRACE_GROUP_MAGNITUDE magnitude
`define DP_TRACE_GROUP_ANCHOR anchor
`define DP_TRACE_GROUP_LEADING leading
`define DP_TRACE_GROUP_SIGN_VALUE sign_value
`define DP_TRACE_GROUP_SPECIAL_VALUE special_value
`else
`define DP_TRACE_GROUP_MAGNITUDE group_align_magnitude
`define DP_TRACE_GROUP_ANCHOR group_align_anchor
`define DP_TRACE_GROUP_LEADING group_align_leading_zero_count
`define DP_TRACE_GROUP_SIGN_VALUE group_align_negative
`define DP_TRACE_GROUP_SPECIAL_VALUE group_align_special
`endif

// Lane register probes: maintained rN names versus frozen SV names.
`ifdef DP_LEGACY_SV
`define DP_TRACE_LANE_PRODUCTS products_q
`define DP_TRACE_LANE_ANCHOR anchor_s2_q
`define DP_TRACE_LANE_LEAVES leaves_q
`else
`define DP_TRACE_LANE_PRODUCTS r2_product_magnitudes
`define DP_TRACE_LANE_ANCHOR r2_group_anchor
`define DP_TRACE_LANE_LEAVES r3_aligned_leaves
`endif

// Compact unpack register probes; only hierarchy/names change, field values do not.
`ifdef DP_LEGACY_SV
`define DP_TRACE_UNPACK_MANTISSAS mantissa_q
`define DP_TRACE_UNPACK_EXPONENTS exponent_q
`define DP_TRACE_UNPACK_SIGNS signs_q
`else
`define DP_TRACE_UNPACK_MANTISSAS r1_mantissas
`define DP_TRACE_UNPACK_EXPONENTS r1_exponents
`define DP_TRACE_UNPACK_SIGNS r1_signs
`endif
