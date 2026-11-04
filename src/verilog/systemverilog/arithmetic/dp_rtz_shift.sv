// One fixed-width logical right barrel shifter. Large counts flush to zero.
// Sign is not present: discarded magnitude bits implement round toward zero.
module dp_rtz_shift #(parameter integer W=27, SHIFT_W=9)(
  input wire [W-1:0] in_magnitude, input wire [SHIFT_W-1:0] in_shift,
  output wire [W-1:0] out_magnitude
);

  // Compare the full amount against W even if W cannot fit in SHIFT_W.
  // Only the barrel-control bits are shortened, after the saturation decision.
  localparam integer WINDOW_COUNT_W=($clog2(W)<1) ? 1 : $clog2(W),
    COUNT_W=(WINDOW_COUNT_W<SHIFT_W) ? WINDOW_COUNT_W : SHIFT_W,
    COMPARE_W=($clog2(W+1)>SHIFT_W) ? $clog2(W+1) : SHIFT_W;
  wire [COMPARE_W-1:0] full_amount={{(COMPARE_W-SHIFT_W){1'b0}},in_shift};
  assign out_magnitude=(full_amount>=W[COMPARE_W-1:0]) ? {W{1'b0}} : in_magnitude >> in_shift[COUNT_W-1:0];
endmodule
