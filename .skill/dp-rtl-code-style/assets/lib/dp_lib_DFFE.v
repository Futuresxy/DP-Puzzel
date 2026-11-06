// DP skill template: WIDTH >= 1; one rising-edge storage boundary.
// R/S variants use synchronous active-low rst_n, before enable.
// Behavioral wrapper, not a technology cell; not in the production file list.
module dp_lib_DFFE #(
  parameter integer WIDTH = 8
) (
  input wire clock,
  input wire in_en,
  input wire [WIDTH-1:0] in_d,
  output wire [WIDTH-1:0] out_q
);

  dp_dff_en #(
    .WIDTH(WIDTH)
  ) ff_storage (
    .clock(clock),
    .in_en(in_en),
    .in_d (in_d),
    .out_q(out_q)
  );

endmodule
