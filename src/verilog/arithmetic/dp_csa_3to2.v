// 三行等权二补码/无符号位向量压为两行；纯组合，无内部进位传播。
// out_carry 已左移一位：in_a+in_b+in_c == out_sum+out_carry (mod 2^W)。
// 上层先符号扩展至足够宽度；此模块不自行解释最高位或饱和。
module dp_csa_3to2 #(
  // 含所有增长位的压缩行宽，至少2位。
  parameter integer W = 43
) (
  input wire [W-1:0] in_a,
  input wire [W-1:0] in_b,
  input wire [W-1:0] in_c,
  output wire [W-1:0] out_sum,
  output wire [W-1:0] out_carry
);
  assign out_sum   = in_a ^ in_b ^ in_c;
  assign out_carry = ((in_a & in_b) | (in_a & in_c) | (in_b & in_c)) << 1;
endmodule
