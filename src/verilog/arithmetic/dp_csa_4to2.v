// 四行压为两行：两个3:2位压缩层，没有中间进位传播加法器。
// carry 为已左移的等权行；两行和等于四个输入和 (mod 2^W)。
module dp_csa_4to2 #(
  // 上层已扩展的二补码/幅值行宽。
  parameter integer W = 43
) (
  input wire [W-1:0] in_a,
  input wire [W-1:0] in_b,
  input wire [W-1:0] in_c,
  input wire [W-1:0] in_d,
  output wire [W-1:0] out_sum,
  output wire [W-1:0] out_carry
);
  // 首层压缩 A/B/C；第二层引入 D。
  wire [W-1:0] first_sum;
  wire [W-1:0] first_carry;
  dp_csa_3to2 #(.W(W)) u_first_compress (
    .in_a      (in_a),
    .in_b      (in_b),
    .in_c      (in_c),
    .out_sum   (first_sum),
    .out_carry (first_carry)
  );
  dp_csa_3to2 #(.W(W)) u_second_compress (
    .in_a      (first_sum),
    .in_b      (first_carry),
    .in_c      (in_d),
    .out_sum   (out_sum),
    .out_carry (out_carry)
  );
endmodule
