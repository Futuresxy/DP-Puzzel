// Parameterized payload register template; WIDTH must be positive.
// One rising-edge storage boundary, no reset, hold when disabled.
// Output is unspecified until the first enabled write; valid masks it.
// Skill asset only: enable does not guarantee clock-gating inference.
module dp_dff_en #(
  parameter integer WIDTH = 1
) (
  input wire clock,
  input wire in_en,
  input wire [WIDTH-1:0] in_d,
  output reg [WIDTH-1:0] out_q
);

  always @(posedge clock) begin
    if (in_en) begin
      out_q <= in_d;
    end
  end

endmodule
