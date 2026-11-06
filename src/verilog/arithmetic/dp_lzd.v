`include "dp_defs.vh"
// Combinational balanced leading-zero detector. Zero returns count=0 and active=0.
// LZD input W=i+f and integer output count.
// Precision / signal | S | I       | F
// ------------------ | - | ------- | -
// Input magnitude    | 0 | i       | f
// Output count       | 0 | COUNT_W | 0
module dp_lzd #(
  parameter integer W = 30,
  parameter integer COUNT_W = $clog2(W + 1)
) (
  input wire [W-1:0] in_magnitude,
  output wire [COUNT_W-1:0] out_count,
  output wire out_active
);

  generate
    if (W == 1) begin : g_bit
      assign out_count  = 0;
      assign out_active = in_magnitude[0];
    end else begin : g_split
      localparam integer LOW  = W / 2;
      localparam integer HIGH = W - LOW;
      wire [$clog2(HIGH+1)-1:0] high_count;
      wire [$clog2(LOW+1)-1:0] low_count;
      wire high_active;
      wire low_active;
      dp_lzd #(
        .W(HIGH)
      ) u_high_detect (
        .in_magnitude(in_magnitude[LOW+:HIGH]),
        .out_count(high_count),
        .out_active(high_active)
      );
      dp_lzd #(
        .W(LOW)
      ) u_low_detect (
        .in_magnitude(in_magnitude[0+:LOW]),
        .out_count(low_count),
        .out_active(low_active)
      );
      assign out_active = high_active | low_active;
      assign out_count = high_active ? {{(COUNT_W - $clog2(
        HIGH + 1
      )) {1'b0}}, high_count} : low_active ? HIGH[COUNT_W-1:0] + {{(COUNT_W - $clog2(
        LOW + 1
      )) {1'b0}}, low_count} : {COUNT_W{1'b0}};
    end
  endgenerate
endmodule
