`include "dp_defs.vh"
// 四组低精度独立 DP；S1–S5 前端 + 五源 S6–S8，L8/II=1。
// 同步低有效复位，原子 A/B/C 接收；只接受该前端支持的浮点类型。
module dp_top_e64 #(
  // 固定四组容量的兼容索引；不表示支持 FP16。
  parameter integer K_FP16 = `DP_DEFAULT_K,
  // 局部幅值窗口，组 token 宽度随之推导。
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  // 全局含符号对齐窗口。
  parameter integer GLOBAL_W = `DP_DEFAULT_GLOBAL_W,
  // 固定四个物理组，不允许运行时或实例级修改容量。
  parameter integer GROUPS = `DP_DEFAULT_K / `DP_GROUP_H
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
  // FP32 累加输入，只在顶层添加一次。
  input wire [`DP_FP32_W-1:0] in_c,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  input wire in_c_datatype,
  // 随请求逐级保存的结束旁带。
  input wire in_last,
  // 输出有效，延迟固定且不支持反压。
  output wire out_valid,
  // S8 最终 FP32 结果，仅在 out_valid 时解释。
  output wire [`DP_FP32_W-1:0] out_d,
  // 数值/scale 编码类型，参与合法组合检查或随结果输出。
  output wire out_d_datatype,
  // 与有效结果同拍的结束旁带。
  output wire out_last
);
  dp_top_lowp #(
      .QE_FRONTEND(0),
      .K_FP16    (K_FP16),
      .LOCAL_W   (LOCAL_W),
      .GLOBAL_W  (GLOBAL_W),
      .GROUPS    (GROUPS)
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
endmodule
