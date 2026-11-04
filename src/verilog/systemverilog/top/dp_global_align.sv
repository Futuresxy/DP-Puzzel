// S6 combinational MAX/one bidirectional shift per source/sign restoration.
// Inputs are statically padded to MAG_W. A_raw already includes each source F.
module dp_global_align #(
  parameter integer N=5, MAG_W=39, ANCHOR_W=10, Z_W=$clog2(MAG_W+1)
)(
  input wire in_integer,in_enable,
  input wire [N*MAG_W-1:0] in_magnitude,
  input wire [N*ANCHOR_W-1:0] in_anchor,
  input wire [N*Z_W-1:0] in_z,
  input wire [N-1:0] in_negative,
  input wire [N*dp_pkg::SPECIAL_W-1:0] in_special,
  output wire [N*(MAG_W+1)-1:0] out_leaves,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  output wire out_negative_zero,
  output dp_pkg::special_t out_special
);
  import dp_pkg::*;
  localparam integer NET_W=ANCHOR_W+1;
  wire [N*ANCHOR_W-1:0] exponents;
  wire [N-1:0] active,negative_zero;
  wire any_active;
  special_t special_comb,source_special;
  assign out_special=special_comb;
  always @* begin
    special_comb='0; source_special='0;
    for(integer i=0;i<N;i=i+1) begin
      source_special=in_special[i*SPECIAL_W+:SPECIAL_W];
      special_comb=merge_special(special_comb,source_special);
    end
  end
  dp_max_tree #(.N(N),.W(ANCHOR_W)) global_anchor_max(
    .in_values(exponents),.in_active(active),.out_max(out_anchor),.out_active(any_active));
  for(genvar i=0;i<N;i=i+1) begin: g_source
    wire signed [ANCHOR_W-1:0] raw_anchor=in_anchor[i*ANCHOR_W+:ANCHOR_W];
    wire [Z_W-1:0] leading=in_z[i*Z_W+:Z_W];
    wire [MAG_W-1:0] magnitude=in_magnitude[i*MAG_W+:MAG_W];
    wire signed [NET_W-1:0] net_shift=$signed({raw_anchor[ANCHOR_W-1],raw_anchor})-$signed({out_anchor[ANCHOR_W-1],out_anchor});
    wire [MAG_W-1:0] isolated_magnitude=active[i] ? magnitude : '0;
    wire [MAG_W-1:0] shifted;
    wire [MAG_W-1:0] result_magnitude=in_integer ? magnitude : shifted;
    assign active[i]=in_enable && !in_integer && magnitude!=0 && in_special[i*SPECIAL_W+:SPECIAL_W]=='0;
    assign exponents[i*ANCHOR_W+:ANCHOR_W]=raw_anchor-$signed(ANCHOR_W'(leading));
    dp_bidir_shift #(.W(MAG_W),.NET_W(NET_W)) global_align_shift(
      .in_magnitude(isolated_magnitude),.in_net(net_shift),.out_magnitude(shifted));
    assign out_leaves[i*(MAG_W+1)+:MAG_W+1]=in_negative[i] ? -$signed({1'b0,result_magnitude}) : $signed({1'b0,result_magnitude});
    assign negative_zero[i]=in_negative[i] && result_magnitude==0;
  end
  assign out_negative_zero=&negative_zero;
endmodule
