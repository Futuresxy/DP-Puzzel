`timescale 1ns/1ps
// Exact signed oracle covers extension masking, each leaf, growth and cancellation.
module dp_mixed_csa_tb;
  parameter integer W = 40;
  parameter integer EXT_GROUPS = 8;
  localparam integer N = 5 + EXT_GROUPS;
  localparam integer SUM_W = W + $clog2(N);
  reg [N*W-1:0] values;
  reg extension_active;
  wire signed [SUM_W-1:0] result;
  reg signed [SUM_W-1:0] expected;
  reg signed [W-1:0] term;
  reg [63:0] random_bits;
  integer vector_index;
  integer term_index;
  integer mode;
  integer seed;
  integer checked;
  dp_mixed_csa_sum #(.EXT_GROUPS(EXT_GROUPS), .W(W)) dut (
    .in_extension_active(extension_active),
    .in_values(values),
    .out_sum(result)
  );
  initial begin
    seed = 192256;
    checked = 0;
    for (mode=0;mode<2;mode=mode+1) begin
      extension_active = mode;
      for(vector_index=0;vector_index<4096+2*N;vector_index=vector_index+1) begin
        values = 0;
        for(term_index=0;term_index<N;term_index=term_index+1) begin
          random_bits = {$random(seed), $random(seed)};
          if(vector_index<2*N)
            term = term_index == vector_index/2 ? (vector_index[0] ?
              {1'b1,{(W-1){1'b0}}} : {1'b0,{(W-1){1'b1}}}) : 0;
          else case(vector_index-2*N)
            0: term = 0;
            1: term = {1'b1,{(W-1){1'b0}}};
            2: term = {1'b0,{(W-1){1'b1}}};
            3: term = -1;
            4: term = term_index[0] ? -1 : 1;
            5: term = term_index[0] ? {1'b1,{(W-1){1'b0}}} : {1'b0,{(W-1){1'b1}}};
            default: term = random_bits[W-1:0];
          endcase
          values[term_index*W+:W] = term;
        end
        #1;
        expected = 0;
        for(term_index=0;term_index<N;term_index=term_index+1) begin
          term = values[term_index*W+:W];
          if(extension_active || term_index<4 || term_index==N-1)
            expected = expected + {{(SUM_W-W){term[W-1]}},term};
        end
        if(result !== expected) begin
          $display("FAIL EXT=%0d W=%0d active=%0d vector=%0d got=%0d expected=%0d",
                   EXT_GROUPS,W,extension_active,vector_index,result,expected);
          $finish;
        end
        checked = checked+1;
      end
    end
    $display("PASS EXT=%0d W=%0d checked=%0d seed=192256",EXT_GROUPS,W,checked);
    $finish;
  end
endmodule
