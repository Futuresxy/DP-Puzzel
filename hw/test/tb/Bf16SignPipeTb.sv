`timescale 1ns/1ps
module Bf16SignPipeTb;
  reg clock = 1'b0;
  reg reset = 1'b1;
  reg in_valid = 1'b0;
  reg in_negate = 1'b0;
  reg [15:0] in_bf16 = 16'h0000;
  wire out_valid;
  wire [15:0] out_bf16;
  string vectors;
  integer handle, fields;
  integer reset_i, valid_i, negate_i, expected_valid, check_hold;
  reg [15:0] input_bits, expected_bits;
  integer cycles = 0;
  integer valid_count = 0;
  integer bubbles = 0;
  integer resets = 0;

  Bf16SignPipe dut (
    .clock(clock), .reset(reset), .in_valid(in_valid), .in_bf16(in_bf16),
    .in_negate(in_negate), .out_valid(out_valid), .out_bf16(out_bf16)
  );
  always #5 clock = ~clock;

  initial begin
    if (!$value$plusargs("vectors=%s", vectors))
      $fatal(1, "Missing +vectors=PATH");
    handle = $fopen(vectors, "r");
    if (handle == 0) $fatal(1, "Cannot open vectors");
    while (!$feof(handle)) begin
      fields = $fscanf(handle, "%d %d %d %h %d %d %h\n",
                       reset_i, valid_i, negate_i, input_bits,
                       expected_valid, check_hold, expected_bits);
      if (fields == 7) begin
        @(negedge clock);
        reset = reset_i;
        in_valid = valid_i;
        in_negate = negate_i;
        in_bf16 = input_bits;
        @(posedge clock);
        #1;
        if (out_valid !== expected_valid[0])
          $fatal(1, "VALID mismatch cycle=%0d actual=%b expected=%b", cycles, out_valid, expected_valid[0]);
        if (expected_valid && out_bf16 !== expected_bits)
          $fatal(1, "NUMERICAL mismatch cycle=%0d actual=%h expected=%h", cycles, out_bf16, expected_bits);
        if (!expected_valid && check_hold && out_bf16 !== expected_bits)
          $fatal(1, "HOLD mismatch cycle=%0d actual=%h expected=%h", cycles, out_bf16, expected_bits);
        cycles = cycles + 1;
        if (reset_i) resets = resets + 1;
        else if (valid_i) valid_count = valid_count + 1;
        else bubbles = bubbles + 1;
      end else if (fields != -1) begin
        $fatal(1, "Malformed vector row");
      end
    end
    $fclose(handle);
    if (valid_count < 131072) $fatal(1, "Exhaustive vector coverage missing");
    $display("BF16_SIGN_PIPE_PASS cycles=%0d valid=%0d bubbles=%0d resets=%0d",
             cycles, valid_count, bubbles, resets);
    $finish;
  end

  initial begin
    #5000000;
    $fatal(1, "Simulation watchdog expired");
  end
endmodule
