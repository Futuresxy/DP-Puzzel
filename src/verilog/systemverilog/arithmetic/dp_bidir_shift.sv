// One right-shift core shared by both directions through static bit reversal.
// Positive net means left, negative means unsigned right/RTZ. No registers.
// DP global float path. Net shift changes the reference exponent.
// Precision / signal | S | I | F
// ------------------ | - | - | ---
// Padded source      | 0 | i | W-i
// Aligned magnitude  | 0 | 1 | W-1
// The operator shifts W unsigned bits in either direction.
module dp_bidir_shift #(parameter integer W=39, NET_W=11)(
  input wire [W-1:0] in_magnitude, input wire signed [NET_W-1:0] in_net,
  output wire [W-1:0] out_magnitude
);
  wire left_direction=!in_net[NET_W-1];
  wire [NET_W-1:0] amount=left_direction ? in_net : -in_net;
  wire [W-1:0] reversed,input_mux,shifted;
  for(genvar i=0;i<W;i=i+1) begin: g_reverse
    assign reversed[i]=in_magnitude[W-1-i];
    assign out_magnitude[i]=left_direction ? shifted[W-1-i] : shifted[i];
  end
  assign input_mux=left_direction ? reversed : in_magnitude;
  dp_rtz_shift #(.W(W),.SHIFT_W(NET_W)) right_shift_core(
    .in_magnitude(input_mux),.in_shift(amount),.out_magnitude(shifted));
endmodule
