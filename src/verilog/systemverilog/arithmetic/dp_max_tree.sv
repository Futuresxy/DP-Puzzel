// Balanced signed MAX with explicit activity. An inactive tree returns zero.
module dp_max_tree #(parameter integer N=4, W=10)(
  input wire [N*W-1:0] in_values, input wire [N-1:0] in_active,
  output wire signed [W-1:0] out_max, output wire out_active
);
  generate if(N==1) begin: g_leaf
    assign out_active=in_active[0];
    assign out_max=in_active[0] ? in_values : {W{1'b0}};
  end else begin: g_branch
    localparam integer LEFT=N/2, RIGHT=N-LEFT;
    wire signed [W-1:0] a,b;
    wire va,vb;
    dp_max_tree #(.N(LEFT),.W(W)) left_tree(
      .in_values(in_values[0+:LEFT*W]),.in_active(in_active[0+:LEFT]),.out_max(a),.out_active(va));
    dp_max_tree #(.N(RIGHT),.W(W)) right_tree(
      .in_values(in_values[LEFT*W+:RIGHT*W]),.in_active(in_active[LEFT+:RIGHT]),.out_max(b),.out_active(vb));
    assign out_active=va|vb;
    assign out_max=va && (!vb || a>=b) ? a : b;
  end endgenerate
endmodule
