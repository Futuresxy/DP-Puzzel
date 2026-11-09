`timescale 1ns/1ps
// Supplemental arithmetic check: exhaustive small signed inputs and wide corner/random inputs.
module dp_csa_tb;
  parameter integer W = 3;
  parameter integer N = 5;
  localparam integer SUM_W = W + $clog2(N);
  reg [N*W-1:0] values;
  wire signed [SUM_W-1:0] result;
  reg signed [SUM_W-1:0] expected;
  reg signed [W-1:0] term;
  reg [63:0] random_bits;
  integer vector_index;
  integer term_index;
  integer count;
  integer seed;
  dp_final_csa_sum #(.N(N), .W(W)) dut (
    .in_values(values),
    .out_sum(result)
  );
  initial begin
    seed = 180927;
    count = W == 3 ? (1 << (N*W)) : 2008;
    for (vector_index=0; vector_index<count; vector_index=vector_index+1) begin
      values = 0;
      for (term_index=0; term_index<N; term_index=term_index+1) begin
        random_bits = {$random(seed), $random(seed)};
        if (W == 3) term = vector_index >> (term_index*W);
        else case(vector_index)
          0: term = 0;
          1: term = {1'b1, {(W-1){1'b0}}};
          2: term = {1'b0, {(W-1){1'b1}}};
          3: term = -1;
          4: term = term_index[0] ? -1 : 1;
          5: term = term_index[0] ? {1'b1, {(W-1){1'b0}}} : {1'b0, {(W-1){1'b1}}};
          6: term = term_index == N-1 ? {1'b1, {(W-1){1'b0}}} : 0;
          7: term = term_index == N-1 ? {1'b0, {(W-1){1'b1}}} : 0;
          default: term = random_bits[W-1:0];
        endcase
        values[term_index*W+:W] = term;
      end
      #1;
      expected = 0;
      for (term_index=0; term_index<N; term_index=term_index+1) begin
        term = values[term_index*W+:W];
        expected = expected + {{(SUM_W-W){term[W-1]}}, term};
      end
      if (result !== expected) begin
        $display("FAIL N=%0d W=%0d vector=%0d got=%0d expected=%0d",N,W,vector_index,result,expected);
        $finish;
      end
    end
    $display("PASS N=%0d W=%0d checked=%0d seed=180927",N,W,count);
    $finish;
  end
endmodule
