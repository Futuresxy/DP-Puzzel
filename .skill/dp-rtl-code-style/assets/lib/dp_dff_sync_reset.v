// Parameterized control register template; WIDTH must be positive.
// One rising-edge storage boundary, synchronous active-low reset.
// Reset takes priority over enable; otherwise hold when disabled.
// Skill asset only: production integration requires the DP RTL regression.
module dp_dff_sync_reset #(
  parameter integer WIDTH = 1,
  parameter [WIDTH-1:0] RESET_VALUE = {WIDTH{1'b0}}
) (
  input wire clock,
  input wire rst_n,
  input wire in_en,
  input wire [WIDTH-1:0] in_d,
  output reg [WIDTH-1:0] out_q
);

  always @(posedge clock) begin
    if (~rst_n) begin
      out_q <= RESET_VALUE;
    end else if (in_en) begin
      out_q <= in_d;
    end
  end

endmodule
