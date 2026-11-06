// DP shared primitive: BIN_W >= 1, 1 <= ONEHOT_W <= 2**BIN_W.
// Zero input returns zero; caller must carry valid to distinguish index zero.
// Multi-hot inputs OR the selected indices and are invalid for encoding.
// This is not a priority encoder. Combinational, no reset.
module dp_lib_onehot2bin #(
  parameter integer BIN_W = 1,
  parameter integer ONEHOT_W = 2
) (
  input wire [ONEHOT_W-1:0] in_onehot,
  output wire [BIN_W-1:0] out_binary
);

  genvar bit_index;
  genvar entry_index;
  generate
    for (bit_index = 0; bit_index < BIN_W; bit_index = bit_index + 1) begin : g_bit
      wire [ONEHOT_W-1:0] selected_bits;
      for (entry_index = 0; entry_index < ONEHOT_W; entry_index = entry_index + 1) begin : g_entry
        localparam [BIN_W-1:0] ENTRY_VALUE = entry_index;
        assign selected_bits[entry_index] = in_onehot[entry_index] & ENTRY_VALUE[bit_index];
      end
      assign out_binary[bit_index] = |selected_bits;
    end
  endgenerate

endmodule
