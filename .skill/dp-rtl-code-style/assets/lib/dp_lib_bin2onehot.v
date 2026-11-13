// DP skill template: BIN_W >= 1, 1 <= ONEHOT_W <= 2**BIN_W.
// Supports non-power-of-two entry counts; out-of-range input returns zero.
// Combinational, no reset. Caller/export validation rejects invalid parameters.
module dp_lib_bin2onehot #(
  parameter integer BIN_W = 1,
  parameter integer ONEHOT_W = 2
) (
  input wire [BIN_W-1:0] in_binary,
  output wire [ONEHOT_W-1:0] out_onehot
);

  genvar entry_index;
  generate
    for (entry_index = 0; entry_index < ONEHOT_W; entry_index = entry_index + 1) begin : g_entry
      localparam [BIN_W-1:0] ENTRY_VALUE = entry_index;
      assign out_onehot[entry_index] = (in_binary == ENTRY_VALUE);
    end
  endgenerate

endmodule
