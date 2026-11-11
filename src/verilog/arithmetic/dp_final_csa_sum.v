// dp_top S7：四个group先4:2，两行与C再3:2，最后唯一一次进位传播加法。
// 纯组合；父层负责 S6/S7 DFF。输入为同一 Emax/F 坐标下的有符号叶子。
// N=2/3/5 对应 K4/8/16；未用 group 静态补零，C 永远只加入一次。
// 浮点 S1I(1+clog2(N))F(W-2)；INT S1I(32+clog2(N))F(W-33)。
module dp_final_csa_sum #(
  // group数加一个C；支持当前单DP的1/2/4组配置。
  parameter integer N = 5,
  // S6 每路补码宽度。
  parameter integer W = 40,
  // 输出增长位由实际输入数决定，不能在压缩层缩窄。
  parameter integer SUM_W = W + $clog2(N)
) (
  input wire [N*W-1:0] in_values,
  output wire signed [SUM_W-1:0] out_sum
);
  // 所有叶子先符号扩展到完整结果宽度，以模2^SUM_W压缩保留负数。
  wire [SUM_W-1:0] group_values [0:3];
  wire [SUM_W-1:0] c_value;
  genvar group_index;
  generate
    for (group_index = 0; group_index < 4; group_index = group_index + 1) begin : g_extend
      if (group_index < N-1) begin : g_active
        assign group_values[group_index] = {{(SUM_W-W){in_values[(group_index+1)*W-1]}}, in_values[group_index*W+:W]};
      end else begin : g_unused
        assign group_values[group_index] = 0;
      end
    end
  endgenerate
  assign c_value = {{(SUM_W-W){in_values[N*W-1]}}, in_values[(N-1)*W+:W]};

  // group 4:2 后的两行，carry 已包含位权，无需再移位。
  wire [SUM_W-1:0] group_sum;
  wire [SUM_W-1:0] group_carry;
  dp_csa_4to2 #(.W(SUM_W)) u_group_compress (
    .in_a      (group_values[0]),
    .in_b      (group_values[1]),
    .in_c      (group_values[2]),
    .in_d      (group_values[3]),
    .out_sum   (group_sum),
    .out_carry (group_carry)
  );

  // 加入 C 后仍保持两行，最后一次 CPA 得到精确有符号结果。
  wire [SUM_W-1:0] total_sum;
  wire [SUM_W-1:0] total_carry;
  dp_csa_3to2 #(.W(SUM_W)) u_c_compress (
    .in_a      (group_sum),
    .in_b      (group_carry),
    .in_c      (c_value),
    .out_sum   (total_sum),
    .out_carry (total_carry)
  );
  assign out_sum = $signed(total_sum) + $signed(total_carry);

  // synthesis translate_off
  initial begin
    if ((N != 2) && (N != 3) && (N != 5)) begin
      $display("ERROR: dp_final_csa_sum requires N=2/3/5");
      $finish;
    end
    if ((W < 2) || (SUM_W < W+$clog2(N))) begin
      $display("ERROR: insufficient carry-save width");
      $finish;
    end
  end
  // synthesis translate_on
endmodule
