// 混合 DP 的 S7 规约：基础四组+C 与扩展2/4/8/12组保持 carry-save 至最终 CPA。
// 纯组合；输入每路为同坐标二补码，父层负责 S6/S7 寄存器。
// W=40: N7 -> S43, N9/N13 -> S44, N17 -> S45.
// carry 行已左移并包含位权；双行 MUX 必须同时选择，不能混用两条路径。
module dp_mixed_csa_sum #(
  // 新增2/4/8/12组，基础组固定为4；不增加流水寄存器。
  parameter integer EXT_GROUPS = 2,
  // S6 每个来源的完整补码位宽。
  parameter integer W = 40,
  // 全部来源（含一次C）的累加增长位。
  parameter integer SUM_W = W + $clog2(5 + EXT_GROUPS)
) (
  // 流水对齐的精度参与选择，不能使用当前输入的datatype。
  input wire in_extension_active,
  // 顺序：基础四组、扩展组、最后一份C。
  input wire [(5+EXT_GROUPS)*W-1:0] in_values,
  output wire signed [SUM_W-1:0] out_sum
);
  // 每个叶子先扩至最终宽度，负数在所有压缩层保留相同的二补码语义。
  wire [SUM_W-1:0] source_values [0:4+EXT_GROUPS];
  genvar source_index;
  generate
    for (source_index = 0; source_index < 5+EXT_GROUPS; source_index = source_index+1) begin : g_extend
      if ((source_index >= 4) & (source_index < 4+EXT_GROUPS)) begin : g_extension
        // 高精度请求隔离扩展压缩支路，DFF保持的旧payload不可参与。
        assign source_values[source_index] = in_extension_active ?
            {{(SUM_W-W){in_values[(source_index+1)*W-1]}}, in_values[source_index*W+:W]} : 0;
      end else begin : g_base
        assign source_values[source_index] =
            {{(SUM_W-W){in_values[(source_index+1)*W-1]}}, in_values[source_index*W+:W]};
      end
    end
  endgenerate

  // 基础四组压成两行，再把C压入，整个基础分支无中间CPA。
  wire [SUM_W-1:0] base_group_sum;
  wire [SUM_W-1:0] base_group_carry;
  wire [SUM_W-1:0] base_sum;
  wire [SUM_W-1:0] base_carry;
  dp_csa_4to2 #(.W(SUM_W)) u_base_group_compress (
    .in_a      (source_values[0]),
    .in_b      (source_values[1]),
    .in_c      (source_values[2]),
    .in_d      (source_values[3]),
    .out_sum   (base_group_sum),
    .out_carry (base_group_carry)
  );
  dp_csa_3to2 #(.W(SUM_W)) u_c_compress (
    .in_a      (base_group_sum),
    .in_b      (base_group_carry),
    .in_c      (source_values[4+EXT_GROUPS]),
    .out_sum   (base_sum),
    .out_carry (base_carry)
  );

  // 扩展2组直接与基础两行做4:2；扩展4组先4:2，再合并基础两行。
  wire [SUM_W-1:0] combined_sum;
  wire [SUM_W-1:0] combined_carry;
  generate
    if (EXT_GROUPS == 2) begin : g_two_groups
      dp_csa_4to2 #(.W(SUM_W)) u_combine (
        .in_a      (base_sum),
        .in_b      (base_carry),
        .in_c      (source_values[4]),
        .in_d      (source_values[5]),
        .out_sum   (combined_sum),
        .out_carry (combined_carry)
      );
    end else if (EXT_GROUPS == 4) begin : g_four_groups
      wire [SUM_W-1:0] extension_sum;
      wire [SUM_W-1:0] extension_carry;
      dp_csa_4to2 #(.W(SUM_W)) u_extension_compress (
        .in_a      (source_values[4]),
        .in_b      (source_values[5]),
        .in_c      (source_values[6]),
        .in_d      (source_values[7]),
        .out_sum   (extension_sum),
        .out_carry (extension_carry)
      );
      dp_csa_4to2 #(.W(SUM_W)) u_combine (
        .in_a      (base_sum),
        .in_b      (base_carry),
        .in_c      (extension_sum),
        .in_d      (extension_carry),
        .out_sum   (combined_sum),
        .out_carry (combined_carry)
      );
    end else begin : g_many_groups
      // Independent four-leaf blocks: 8 -> 4 rows, or 12 -> 6 rows.
      localparam integer BLOCK_COUNT = EXT_GROUPS / 4;
      wire [SUM_W-1:0] block_sum [0:BLOCK_COUNT-1];
      wire [SUM_W-1:0] block_carry [0:BLOCK_COUNT-1];
      genvar block_index;
      for (block_index = 0; block_index < BLOCK_COUNT; block_index = block_index+1) begin : g_block
        dp_csa_4to2 #(.W(SUM_W)) u_compress (
          .in_a      (source_values[4+block_index*4]),
          .in_b      (source_values[5+block_index*4]),
          .in_c      (source_values[6+block_index*4]),
          .in_d      (source_values[7+block_index*4]),
          .out_sum   (block_sum[block_index]),
          .out_carry (block_carry[block_index])
        );
      end
      // First eight leaves reduce to two rows using exactly three 4:2 units.
      wire [SUM_W-1:0] first_eight_sum;
      wire [SUM_W-1:0] first_eight_carry;
      wire [SUM_W-1:0] extension_sum;
      wire [SUM_W-1:0] extension_carry;
      dp_csa_4to2 #(.W(SUM_W)) u_first_eight_compress (
        .in_a      (block_sum[0]),
        .in_b      (block_carry[0]),
        .in_c      (block_sum[1]),
        .in_d      (block_carry[1]),
        .out_sum   (first_eight_sum),
        .out_carry (first_eight_carry)
      );
      if (EXT_GROUPS == 8) begin : g_eight_groups
        assign extension_sum   = first_eight_sum;
        assign extension_carry = first_eight_carry;
      end else begin : g_twelve_groups
        // The third block and this merge bring the extension count to five.
        dp_csa_4to2 #(.W(SUM_W)) u_last_four_compress (
          .in_a      (first_eight_sum),
          .in_b      (first_eight_carry),
          .in_c      (block_sum[2]),
          .in_d      (block_carry[2]),
          .out_sum   (extension_sum),
          .out_carry (extension_carry)
        );
      end
      // Base+C and extension are still two rows each; one final 4:2 joins them.
      dp_csa_4to2 #(.W(SUM_W)) u_combine (
        .in_a      (base_sum),
        .in_b      (base_carry),
        .in_c      (extension_sum),
        .in_d      (extension_carry),
        .out_sum   (combined_sum),
        .out_carry (combined_carry)
      );
    end
  endgenerate

  // 只有这里做进位传播；高精度路径通过MUX旁路扩展压缩层。
  wire [SUM_W-1:0] selected_sum;
  wire [SUM_W-1:0] selected_carry;
  assign selected_sum   = in_extension_active ? combined_sum : base_sum;
  assign selected_carry = in_extension_active ? combined_carry : base_carry;
  assign out_sum        = $signed(selected_sum) + $signed(selected_carry);

  // synthesis translate_off
  initial begin
    if ((EXT_GROUPS != 2) && (EXT_GROUPS != 4) && (EXT_GROUPS != 8) && (EXT_GROUPS != 12)) begin
      $display("ERROR: dp_mixed_csa_sum requires 2/4/8/12 extension groups");
      $finish;
    end
    if (SUM_W < W+$clog2(5+EXT_GROUPS)) begin
      $display("ERROR: dp_mixed_csa_sum insufficient output width");
      $finish;
    end
  end
  // synthesis translate_on
endmodule
