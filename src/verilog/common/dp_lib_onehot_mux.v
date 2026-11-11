// DP shared primitive: N >= 1, W >= 1. Input i occupies [i*W +: W].
// Zero select returns zero. Multiple selects OR their data, not priority;
// callers must enforce one-hot-or-zero selection. Combinational, no reset.
module dp_lib_onehot_mux #(
  parameter integer N = 1,
  parameter integer W = 1
) (
  input  wire [  N-1:0] in_select,
  input  wire [N*W-1:0] in_data,
  output wire [  W-1:0] out_data
);

  genvar bit_index;
  genvar entry_index;
  generate
    for (bit_index = 0; bit_index < W; bit_index = bit_index + 1) begin : g_bit
      wire [N-1:0] selected_bits;
      for (entry_index = 0; entry_index < N; entry_index = entry_index + 1) begin : g_entry
        assign
          selected_bits[entry_index] = in_select[entry_index] & in_data[entry_index*W+bit_index];
      end
      assign out_data[bit_index] = |selected_bits;
    end
  endgenerate

endmodule
