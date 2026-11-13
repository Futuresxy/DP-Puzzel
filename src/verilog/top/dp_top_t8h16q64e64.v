`include "dp_defs.vh"
// Four baseline groups plus four Q-only groups: T8/H16/Q64/E64, L8/II=1.
// Extension groups accept only Q requests; all other modes retain base capacity.
module dp_top_t8h16q64e64 #(
  // 高精度基线并行度，混合顶层固定为 16。
  parameter integer K_FP16 = `DP_DEFAULT_K,
  // S3 局部幅值对齐窗口，改变时下游 lane/group 位宽同步推导。
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  // S6 有符号对齐叶子位宽；含一个符号位。
  parameter integer GLOBAL_W = `DP_DEFAULT_GLOBAL_W,
  // Static extension capabilities; high-precision base capacity remains K_FP16=16.
  parameter integer EXT_GROUPS = 4,
  // 多精度基线 group 数量，保持为四组。
  parameter integer BASE_GROUPS = `DP_DEFAULT_K / `DP_GROUP_H,
  // 物理 group 总数，包含基线与新增组。
  parameter integer GROUPS = BASE_GROUPS + EXT_GROUPS
) (
  // 上升沿流水时钟。
  input wire clock,
  // 同步低有效复位，只复位控制；数据由 valid 屏蔽。
  input wire rst_n,
  // 该操作数独立 valid；三路齐备且类型合法时才原子接收。
  input wire in_a_valid,
  // 该操作数独立 valid；三路齐备且类型合法时才原子接收。
  input wire in_b_valid,
  // 该操作数独立 valid；三路齐备且类型合法时才原子接收。
  input wire in_c_valid,
  // 原子接收回执，与另外两路 ready 同拍一致。
  output wire out_a_ready,
  // 原子接收回执，与另外两路 ready 同拍一致。
  output wire out_b_ready,
  // 原子接收回执，与另外两路 ready 同拍一致。
  output wire out_c_ready,
  // A 原始打包操作数，按 group/lane 低位优先切片。
  input wire [GROUPS*`DP_LANES*`DP_LANE_W-1:0] in_a,
  // B 原始打包操作数，与 A 同容量且逐元素配对。
  input wire [GROUPS*`DP_LANES*`DP_LANE_W-1:0] in_b,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire [`DP_TYPE_W-1:0] in_a_datatype,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire [`DP_TYPE_W-1:0] in_b_datatype,
  // A 的每组 scale 字节，由测试/上游按格式广播到各组。
  input wire [GROUPS*`DP_SCALE_W-1:0] in_scale_a,
  // B 的每组 scale 字节，布局与 A 一致。
  input wire [GROUPS*`DP_SCALE_W-1:0] in_scale_b,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_a_datatype,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_b_datatype,
  // HiF4 e1 元数据，每位对应四个元素。
  input wire [GROUPS*4-1:0] in_hif4_e1_a,
  // HiF4 e1 元数据，每位对应四个元素。
  input wire [GROUPS*4-1:0] in_hif4_e1_b,
  // HiF4 e2 元数据，每位对应一个八元素 lane。
  input wire [GROUPS*2-1:0] in_hif4_e2_a,
  // HiF4 e2 元数据，每位对应一个八元素 lane。
  input wire [GROUPS*2-1:0] in_hif4_e2_b,
  // FP32/INT32 累加输入，只在顶层添加一次。
  input wire [`DP_FP32_W-1:0] in_c,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire in_c_datatype,
  // 随请求逐级保存的结束旁带。
  input wire in_last,
  // 输出有效，延迟固定且不支持反压。
  output wire out_valid,
  // S8 最终 FP32/INT32 结果，仅在 out_valid 时解释。
  output wire [`DP_FP32_W-1:0] out_d,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  output wire out_d_datatype,
  // 与有效结果同拍的结束旁带。
  output wire out_last
);
  dp_top_mixed #(
      .OPTIMIZE_QE(1),
      .EXT_Q_ONLY(1),
      .K_FP16    (K_FP16),
      .LOCAL_W   (LOCAL_W),
      .GLOBAL_W  (GLOBAL_W),
      .EXT_GROUPS(EXT_GROUPS),
      .EXT_QE    (0)
  ) u_core (
      .clock              (clock),
      .rst_n              (rst_n),
      .in_a_valid         (in_a_valid),
      .in_b_valid         (in_b_valid),
      .in_c_valid         (in_c_valid),
      .out_a_ready        (out_a_ready),
      .out_b_ready        (out_b_ready),
      .out_c_ready        (out_c_ready),
      .in_a               (in_a),
      .in_b               (in_b),
      .in_a_datatype      (in_a_datatype),
      .in_b_datatype      (in_b_datatype),
      .in_scale_a         (in_scale_a),
      .in_scale_b         (in_scale_b),
      .in_scale_a_datatype(in_scale_a_datatype),
      .in_scale_b_datatype(in_scale_b_datatype),
      .in_hif4_e1_a       (in_hif4_e1_a),
      .in_hif4_e1_b       (in_hif4_e1_b),
      .in_hif4_e2_a       (in_hif4_e2_a),
      .in_hif4_e2_b       (in_hif4_e2_b),
      .in_c               (in_c),
      .in_c_datatype      (in_c_datatype),
      .in_last            (in_last),
      .out_valid          (out_valid),
      .out_d              (out_d),
      .out_d_datatype     (out_d_datatype),
      .out_last           (out_last)
  );
  // synthesis translate_off
  initial begin
    if (EXT_GROUPS != 4 || GROUPS != 8 || BASE_GROUPS != 4) begin
      $display("ERROR: fixed profile mismatch");
      $finish;
    end
  end
  // synthesis translate_on
endmodule
