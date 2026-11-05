`include "dp_defs.vh"
// Combinational balanced leading-zero detector. Zero returns count=0 and active=0.
// Input unsigned S0I(i)F(f), W=i+f. Output is an unsigned count (F0).
module dp_lzd #(parameter integer W=30, COUNT_W=$clog2(W+1))(
  input wire [W-1:0] in_magnitude,
  output wire [COUNT_W-1:0] out_count, output wire out_active
);

  generate if(W==1) begin: g_bit
    assign out_count=0;
    assign out_active=in_magnitude[0];
  end else begin: g_split
    localparam integer LOW=W/2, HIGH=W-LOW;
    wire [$clog2(HIGH+1)-1:0] hc;
    wire [$clog2(LOW+1)-1:0] lc;
    wire ha,la;
    dp_lzd #(.W(HIGH)) high_detect(.in_magnitude(in_magnitude[LOW+:HIGH]),.out_count(hc),.out_active(ha));
    dp_lzd #(.W(LOW)) low_detect(.in_magnitude(in_magnitude[0+:LOW]),.out_count(lc),.out_active(la));
    assign out_active=ha|la;
    assign out_count=ha ? {{(COUNT_W-$clog2(HIGH+1)){1'b0}},hc} :
      la ? HIGH[COUNT_W-1:0]+{{(COUNT_W-$clog2(LOW+1)){1'b0}},lc} : {COUNT_W{1'b0}};
  end endgenerate
endmodule
