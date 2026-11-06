`include "dp_defs.vh"
// Combinational decoder for one E8 operand (32 bits); instantiated for A and B.
// MXFP4/NVFP4/HiF4 only; the top rejects unsupported datatypes.
// No clock/reset/handshake or registers. dp_lane_e captures outputs at S1.
// Sign is independent, including signed zero. HiF4 e1 covers four elements;
// e2 stays in the lane control path and is applied after the lane sum.
// Precision    | Magnitude S | I | F | Separate sign bits per element
// ------------ | ----------- | - | - | ------------------------------
// MXFP4/NVFP4  | 0           | 3 | 1 | 1
// HiF4 (e1 in) | 0           | 2 | 2 | 1
module dp_lane_unpack_e (
  input wire [`DP_LANE_W-1:0] in_data,
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire [1:0] in_e1,
  output wire [`DP_E_LANES*`DP_MUL_LO-1:0] out_magnitude,
  output wire [`DP_E_LANES-1:0] out_negative
);
  function [`DP_MUL_LO-1:0] decode_magnitude;
    input [3:0] raw;
    input hif, e1;
    begin
      if (hif) decode_magnitude = {1'b0, raw[2:0]} << e1;
      else
        case (raw[2:0])
          3'd0: decode_magnitude = 4'd0;
          3'd1: decode_magnitude = 4'd1;
          3'd2: decode_magnitude = 4'd2;
          3'd3: decode_magnitude = 4'd3;
          3'd4: decode_magnitude = 4'd4;
          3'd5: decode_magnitude = 4'd6;
          3'd6: decode_magnitude = 4'd8;
          default: decode_magnitude = 4'd12;
        endcase
    end
  endfunction
  genvar j;
  generate
    for (j = 0; j < `DP_E_LANES; j = j + 1) begin : g_element
      assign out_magnitude[j*`DP_MUL_LO+:`DP_MUL_LO] = decode_magnitude(
        in_data[j*4+:4], in_datatype == `DP_DT_HIF4, in_e1[j/4]
      );
      assign out_negative[j] = in_data[j*4+3];
    end
  endgenerate
endmodule
