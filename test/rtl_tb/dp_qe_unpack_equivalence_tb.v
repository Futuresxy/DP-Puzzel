`timescale 1ns/1ps
`include "dp_defs.vh"
// 新旧 QE 解包 S1 对照：全 Q 编码对、E 编码/元数据、混合随机与保持。
// 旧模块在 S1 后配对，优化模块在 S1 前配对，S2 可见数据必须相同。
module dp_qe_unpack_equivalence_tb;
  reg clock = 0;
  reg rst_n = 0;
  reg in_valid = 0;
  reg [`DP_TYPE_W-1:0] datatype = 0;
  reg [`DP_TYPE_W-1:0] r1_datatype = 0;
  reg [31:0] operand_a = 0;
  reg [31:0] operand_b = 0;
  reg [1:0] e1_a = 0;
  reg [1:0] e1_b = 0;
  reg e2_a = 0;
  reg e2_b = 0;
  integer checks = 0;
  integer mode;
  integer code_a;
  integer code_b;
  integer metadata;
  integer sample_index;
  reg [31:0] random_state = 32'h71e0cafe;
  always @(posedge clock) if (rst_n && in_valid) r1_datatype <= datatype;
  wire [`DP_UNPACK_MANT_W-1:0] reference_a_mantissas;
  wire [`DP_UNPACK_MANT_W-1:0] reference_b_mantissas;
  wire [`DP_UNPACK_EXP_W-1:0] reference_a_exponents;
  wire [`DP_UNPACK_EXP_W-1:0] reference_b_exponents;
  wire [`DP_E_LANES-1:0] reference_product_negative;
  wire [`DP_E_LANES-1:0] reference_product_active;
  wire [`DP_SPECIAL_W-1:0] reference_special;
  wire [1-1:0] reference_all_negative;
  dp_lane_unpack #(.QE_ONLY(1)) u_reference (
    .clock(clock),
    .rst_n(rst_n),
    .in_valid(in_valid),
    .in_datatype(datatype),
    .in_a(operand_a),
    .in_b(operand_b),
    .in_e1_a(e1_a),
    .in_e1_b(e1_b),
    .in_e2_a(e2_a),
    .in_e2_b(e2_b),
    .in_registered_datatype(r1_datatype),
    .out_a_signs(),
    .out_b_signs(),
    .out_a_mantissas(reference_a_mantissas),
    .out_b_mantissas(reference_b_mantissas),
    .out_a_exponents(reference_a_exponents),
    .out_b_exponents(reference_b_exponents),
    .out_product_negative(reference_product_negative),
    .out_product_active(reference_product_active),
    .out_special(reference_special),
    .out_all_negative(reference_all_negative)
  );
  wire [`DP_UNPACK_MANT_W-1:0] optimized_a_mantissas;
  wire [`DP_UNPACK_MANT_W-1:0] optimized_b_mantissas;
  wire [`DP_UNPACK_EXP_W-1:0] optimized_a_exponents;
  wire [`DP_UNPACK_EXP_W-1:0] optimized_b_exponents;
  wire [`DP_E_LANES-1:0] optimized_product_negative;
  wire [`DP_E_LANES-1:0] optimized_product_active;
  wire [`DP_SPECIAL_W-1:0] optimized_special;
  wire [1-1:0] optimized_all_negative;
  dp_lane_unpack_qe u_optimized (
    .clock(clock),
    .rst_n(rst_n),
    .in_valid(in_valid),
    .in_datatype(datatype),
    .in_a(operand_a),
    .in_b(operand_b),
    .in_e1_a(e1_a),
    .in_e1_b(e1_b),
    .in_e2_a(e2_a),
    .in_e2_b(e2_b),
    .out_a_mantissas(optimized_a_mantissas),
    .out_b_mantissas(optimized_b_mantissas),
    .out_a_exponents(optimized_a_exponents),
    .out_b_exponents(optimized_b_exponents),
    .out_product_negative(optimized_product_negative),
    .out_product_active(optimized_product_active),
    .out_special(optimized_special),
    .out_all_negative(optimized_all_negative)
  );
  task tick_and_check;
    begin
      #1; clock = 1;
      #1;
      if (reference_a_mantissas !== optimized_a_mantissas) begin
        $display("a_mantissas mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_b_mantissas !== optimized_b_mantissas) begin
        $display("b_mantissas mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_a_exponents !== optimized_a_exponents) begin
        $display("a_exponents mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_b_exponents !== optimized_b_exponents) begin
        $display("b_exponents mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_product_negative !== optimized_product_negative) begin
        $display("product_negative mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_product_active !== optimized_product_active) begin
        $display("product_active mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_special !== optimized_special) begin
        $display("special mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      if (reference_all_negative !== optimized_all_negative) begin
        $display("all_negative mismatch check=%0d mode=%0d A=%h B=%h", checks, datatype, operand_a, operand_b);
        $stop;
      end
      checks = checks + 1;
      clock = 0;
    end
  endtask
  task random_step;
    begin
      random_state = random_state ^ (random_state << 13);
      random_state = random_state ^ (random_state >> 17);
      random_state = random_state ^ (random_state << 5);
    end
  endtask
  initial begin
    rst_n = 1;
    in_valid = 1;
    // Q 每个字节全部编码对。槽1反转符号，使同拍出现正负 Inf 冲突。
    for (mode = 3; mode <= 6; mode = mode + 1) begin
      datatype = mode;
      for (code_a = 0; code_a < 256; code_a = code_a + 1)
        for (code_b = 0; code_b < 256; code_b = code_b + 1) begin
          operand_a = {4{code_a[7:0]}} ^ 32'h00008000;
          operand_b = {4{code_b[7:0]}};
          tick_and_check;
        end
    end
    // E 全编码对、两侧全部 e1/e2；既覆盖最大值，也覆盖负零。
    for (mode = 7; mode <= 9; mode = mode + 1) begin
      datatype = mode;
      for (code_a = 0; code_a < 16; code_a = code_a + 1)
        for (code_b = 0; code_b < 16; code_b = code_b + 1)
          for (metadata = 0; metadata < 64; metadata = metadata + 1) begin
            operand_a = {8{code_a[3:0]}};
            operand_b = {8{code_b[3:0]}};
            {e1_a, e1_b, e2_a, e2_b} = metadata[5:0];
            tick_and_check;
          end
    end
    // 各槽独立随机值，检查 atom 重排、逐拍换型、气泡及同步复位保持。
    for (sample_index = 0; sample_index < 8192; sample_index = sample_index + 1) begin
      random_step;
      operand_a = random_state;
      datatype = 3 + random_state % 7;
      random_step;
      operand_b = random_state;
      {e1_a, e1_b, e2_a, e2_b} = random_state[5:0];
      in_valid = sample_index % 11 != 0;
      rst_n = sample_index % 31 != 0;
      tick_and_check;
    end
    $display("QE_UNPACK_EQUIVALENCE PASS checks=%0d seed=71e0cafe", checks);
    $finish;
  end
endmodule
