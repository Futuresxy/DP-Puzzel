`include "dp_defs.vh"
// S6 combinational MAX/one bidirectional shift per source/sign restoration.
// Inputs are statically padded to MAG_W. A_raw already includes each source F.
// Floating input pad preserves I and adds MAG_W-M_src to F. A_raw sets
// its coordinate. Shift output is S0I1F(MAG_W-1) at E_max; restore
// the sign for TC S1I1F(MAG_W-1). INT8+INT32 bypasses the shift
// and restores the sign for TC S1I32F(MAG_W-32).
module dp_global_align #(
  parameter integer N=5, MAG_W=39, ANCHOR_W=10, Z_W=$clog2(MAG_W+1)
)(
  input wire in_integer,in_enable,
  input wire [N*MAG_W-1:0] in_magnitude,
  input wire [N*ANCHOR_W-1:0] in_anchor,
  input wire [N*Z_W-1:0] in_z,
  input wire [N-1:0] in_negative,
  input wire [N*`DP_SPECIAL_W-1:0] in_special,
  output wire [N*(MAG_W+1)-1:0] out_leaves,
  output wire signed [ANCHOR_W-1:0] out_anchor,
  output wire out_negative_zero,
  output wire [`DP_SPECIAL_W-1:0] out_special
);
  genvar gen_i;
  integer i;

  `include "dp_functions.vh"
  localparam integer NET_W=ANCHOR_W+1;
  wire [N*ANCHOR_W-1:0] exponents;
  wire [N-1:0] active,negative_zero;
  wire any_active;
  reg [`DP_SPECIAL_W-1:0] special_comb,source_special;
  assign out_special=special_comb;
  always @* begin
    special_comb=0; source_special=0;
    for(i=0;i<N;i=i+1) begin
      source_special=in_special[i*`DP_SPECIAL_W+:`DP_SPECIAL_W];
      special_comb=merge_special(special_comb,source_special);
    end
  end
  dp_max_tree #(.N(N),.W(ANCHOR_W)) global_anchor_max(
    .in_values(exponents),.in_active(active),.out_max(out_anchor),.out_active(any_active));
  generate
  for(gen_i=0;gen_i<N;gen_i=gen_i+1) begin: g_source
    wire signed [ANCHOR_W-1:0] raw_anchor=in_anchor[gen_i*ANCHOR_W+:ANCHOR_W];
    wire [Z_W-1:0] leading=in_z[gen_i*Z_W+:Z_W];
    wire [MAG_W-1:0] magnitude=in_magnitude[gen_i*MAG_W+:MAG_W];
    wire signed [NET_W-1:0] net_shift=$signed({raw_anchor[ANCHOR_W-1],raw_anchor})-$signed({out_anchor[ANCHOR_W-1],out_anchor});
    wire [MAG_W-1:0] isolated_magnitude=active[gen_i] ? magnitude : 0;
    wire [MAG_W-1:0] shifted;
    wire [MAG_W-1:0] result_magnitude=in_integer ? magnitude : shifted;
    assign active[gen_i]=in_enable && !in_integer && magnitude!=0 && in_special[gen_i*`DP_SPECIAL_W+:`DP_SPECIAL_W]==0;
    assign exponents[gen_i*ANCHOR_W+:ANCHOR_W]=raw_anchor-$signed({{(ANCHOR_W-Z_W){1'b0}},leading});
    dp_bidir_shift #(.W(MAG_W),.NET_W(NET_W)) global_align_shift(
      .in_magnitude(isolated_magnitude),.in_net(net_shift),.out_magnitude(shifted));
    assign out_leaves[gen_i*(MAG_W+1)+:MAG_W+1]=in_negative[gen_i] ? -$signed({1'b0,result_magnitude}) : $signed({1'b0,result_magnitude});
    assign negative_zero[gen_i]=in_negative[gen_i] && result_magnitude==0;
  end endgenerate
  assign out_negative_zero=&negative_zero;
endmodule
