`include "dp_defs.vh"
// Balanced signed reduction. Odd final leaves are sign extended, never dropped.
// No registers; natural output growth is ceil(log2(N)). N=1 is a wire.
module dp_sum_tree #(parameter integer N=4, W=28)(
  input wire [N*W-1:0] in_values,
  output wire signed [W+$clog2(N)-1:0] out_sum
);
  genvar i;

  generate if(N==1) begin: g_leaf
    assign out_sum=$signed(in_values);
  end else begin: g_level
    localparam integer NEXT_N=(N+1)/2;
    wire [NEXT_N*(W+1)-1:0] next_values;
    for(i=0;i<NEXT_N;i=i+1) begin: g_pair
      wire signed [W-1:0] a=in_values[(2*i)*W+:W];
      if(2*i+1<N) begin: g_two
        wire signed [W-1:0] b=in_values[(2*i+1)*W+:W];
        assign next_values[i*(W+1)+:W+1]=$signed({a[W-1],a})+$signed({b[W-1],b});
      end else begin: g_odd
        assign next_values[i*(W+1)+:W+1]={a[W-1],a};
      end
    end
    dp_sum_tree #(.N(NEXT_N),.W(W+1)) next_level(.in_values(next_values),.out_sum(out_sum));
  end endgenerate
endmodule
