`include "dp_defs.vh"
// 四组 E/QE 共用顶层核心：静态选择前端，S5 token 后共享五源浮点后端。
// L8/II=1；原子接收 A/B/C，无输出反压；同步低有效 rst_n 清除 valid。
// E/HiF 的 group 坐标沿用其自身算法，S6 只消费 token，不按类型再次修正 F。
// S6 含符号对齐叶子和 S7 完整累加和（TC）：
// 精度                  | S | I | F
// MXFP8 / MXFP6，S6     | 1 | 1 | GLOBAL_W-2
// MXFP4/NVFP4/HiF4，S6  | 1 | 1 | GLOBAL_W-2
// MXFP8 / MXFP6，S7     | 1 | 4 | GLOBAL_W-2
// MXFP4/NVFP4/HiF4，S7  | 1 | 4 | GLOBAL_W-2
// S8 仅输出 FP32，1/8/23 是编码域，非定点 S/I/F。
module dp_top_lowp #(
  // 静态前端：0=E-only，1=紧凑 QE；仅生成所选 group。
  parameter integer QE_FRONTEND = 0,
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
  genvar group_index;

  `include "dp_functions.vh"
  // S5 group 幅值容器宽度（不含单独符号）。
  localparam integer GROUP_MAG_W = LOCAL_W + 3;
  // S6 全局幅值窗口宽度（不含符号）。
  localparam integer GLOBAL_MAG_W = GLOBAL_W - 1;
  // 四组加 C，五个独立对齐来源。
  localparam integer SOURCE_COUNT = GROUPS + 1;
  // 五项完整规约增加 ceil(log2(5)) 个整数位。
  localparam integer SUM_W = GLOBAL_W + $clog2(SOURCE_COUNT);
  // 有符号指数坐标宽度由全局窗口推导。
  localparam integer ANCHOR_W = anchor_width(GLOBAL_MAG_W);
  // 全局幅值前导零计数宽度。
  localparam integer Z_W = $clog2(GLOBAL_MAG_W + 1);
  // [输入协议] 只有三路 valid 同时有效、datatype/scale 元组合法且 rst_n=1 才接收。
  // 缺一路只注入 bubble，不冻结已接收的事务；ready 表示本拍三路共同接收。
  // 允许的格式族与完整请求元组合法性；静态 QE_FRONTEND 裁剪 Q 判断。
  wire tuple_legal;
  wire e_type;
  wire q_type;
  assign e_type      = (in_a_datatype == `DP_DT_MXFP4) | (in_a_datatype == `DP_DT_NVFP4) |
                       (in_a_datatype == `DP_DT_HIF4);
  assign q_type      = (in_a_datatype == `DP_DT_MX8_E4M3) | (in_a_datatype == `DP_DT_MX8_E5M2) |
                       (in_a_datatype == `DP_DT_MX6_E2M3) | (in_a_datatype == `DP_DT_MX6_E3M2);
  assign tuple_legal = (e_type | ((QE_FRONTEND != 0) & q_type)) &
                      (in_a_datatype == in_b_datatype) & ~in_c_datatype &
                      (in_scale_a_datatype == scale_type(in_a_datatype)) &
                      (in_scale_b_datatype == scale_type(in_a_datatype));
  // 本拍原子接收事件，同时驱动四组和 C/控制流水。
  wire req_fire;
  assign req_fire    = rst_n & in_a_valid & in_b_valid & in_c_valid & tuple_legal;
  assign out_a_ready = req_fire;
  assign out_b_ready = req_fire;
  assign out_c_ready = req_fire;
  // S1 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r1_valid;
  wire r1_last;
  // S2 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r2_valid;
  wire r2_last;
  // S3 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r3_valid;
  wire r3_last;
  // S4 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r4_valid;
  wire r4_last;
  // S5 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r5_valid;
  wire r5_last;
  // S6 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r6_valid;
  wire r6_last;
  // S7 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r7_valid;
  wire r7_last;
  // S8 控制寄存值：valid 传播气泡，last 与事务同步。
  wire r8_valid;
  wire r8_last;
  assign out_valid      = r8_valid;
  assign out_last       = r8_last & out_valid;
  assign out_d_datatype = 1'b0;
  // [S1-S5 group 前端] G=K_FP16/4，每 group 消费两个连续 32 位 lane。
  // K16 时为四个 group；source 槽 0..G-1 放组结果，槽 G 放 C。
  // 低位补零将各来源幅值放入 GLOBAL_MAG_W；不是新增有效精度或动态移位。
  wire [SOURCE_COUNT*GLOBAL_MAG_W-1:0] source_magnitude;
  wire [SOURCE_COUNT*ANCHOR_W-1:0] source_anchor;
  wire [SOURCE_COUNT*ANCHOR_W-1:0] source_compare_exp;
  wire [SOURCE_COUNT*Z_W-1:0] source_z;
  wire [SOURCE_COUNT-1:0] source_negative;
  wire [SOURCE_COUNT*`DP_SPECIAL_W-1:0] source_special;
  generate
    for (group_index = 0; group_index < GROUPS; group_index = group_index + 1) begin : g_group
      wire [GROUP_MAG_W-1:0] group_align_magnitude;
      wire signed [ANCHOR_W-1:0] group_align_anchor;
      wire signed [ANCHOR_W-1:0] group_align_compare_exp;
      wire [$clog2(GROUP_MAG_W+1)-1:0] group_align_leading_zero_count;
      wire group_align_negative;
      wire group_top_valid;
      wire [`DP_SPECIAL_W-1:0] group_align_special;
      if (QE_FRONTEND != 0) begin : g_qe
        dp_group_qe #(
          .ARCHITECTURE_V19     (1),
          .COMPACT_UNPACK       (1),
          .LOCAL_W              (LOCAL_W),
          .ANCHOR_W             (ANCHOR_W)
        ) u_group_unit (
          .clock                (clock),
          .rst_n                (rst_n),
          .in_valid             (req_fire),
          .in_datatype          (in_a_datatype),
          .in_a                 (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
          .in_b                 (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
          .in_scale_a           (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
          .in_scale_b           (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
          .in_scale_datatype    (in_scale_a_datatype),
          .in_e1_a              (in_hif4_e1_a[group_index*4+:4]),
          .in_e1_b              (in_hif4_e1_b[group_index*4+:4]),
          .in_e2_a              (in_hif4_e2_a[group_index*2+:2]),
          .in_e2_b              (in_hif4_e2_b[group_index*2+:2]),
          .out_valid            (group_top_valid),
          .out_negative         (group_align_negative),
          .out_magnitude        (group_align_magnitude),
          .out_anchor           (group_align_anchor),
          .out_compare_exp      (group_align_compare_exp),
          .out_z                (group_align_leading_zero_count),
          .out_special          (group_align_special)
        );
      end else begin : g_e
        dp_group_e #(
          .LOCAL_W              (LOCAL_W),
          .ANCHOR_W             (ANCHOR_W)
        ) u_group_unit (
          .clock                (clock),
          .rst_n                (rst_n),
          .in_valid             (req_fire),
          .in_datatype          (in_a_datatype),
          .in_a                 (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
          .in_b                 (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
          .in_scale_a           (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
          .in_scale_b           (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
          .in_scale_datatype    (in_scale_a_datatype),
          .in_e1_a              (in_hif4_e1_a[group_index*4+:4]),
          .in_e1_b              (in_hif4_e1_b[group_index*4+:4]),
          .in_e2_a              (in_hif4_e2_a[group_index*2+:2]),
          .in_e2_b              (in_hif4_e2_b[group_index*2+:2]),
          .out_valid            (group_top_valid),
          .out_negative         (group_align_negative),
          .out_magnitude        (group_align_magnitude),
          .out_anchor           (group_align_anchor),
          .out_compare_exp      (group_align_compare_exp),
          .out_z                (group_align_leading_zero_count),
          .out_special          (group_align_special)
        );
      end
      assign source_magnitude[group_index*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {
        group_align_magnitude, {(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}
      };
      assign source_negative[group_index]                  = group_align_negative;
      assign source_anchor[group_index*ANCHOR_W+:ANCHOR_W] = group_align_anchor;
      assign source_compare_exp[group_index*ANCHOR_W+:ANCHOR_W] = group_align_compare_exp;
      assign source_z[group_index*Z_W+:Z_W] = {
        {(Z_W - $clog2(GROUP_MAG_W + 1)) {1'b0}}, group_align_leading_zero_count
      };
      assign source_special[group_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] = group_align_special;
    end
  endgenerate
  // [S1-S4 C/控制传递] group 内执行前端计算；本层同拍传递 C 和请求旁带。

  // S1 C 原始编码，只在上一拍有效时保存。
  wire [`DP_FP32_W-1:0] r1_c_raw;
  // [S1 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(req_fire), .out_q(r1_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_last (.clock(clock), .rst_n(rst_n), .in_d(req_fire & in_last), .out_q(r1_last));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s0_s1_c_raw (.clock(clock), .in_en(rst_n & req_fire), .in_d(in_c), .out_q(r1_c_raw));
  // verilog_format: on

  // S2 C 原始编码，只在上一拍有效时保存。
  wire [`DP_FP32_W-1:0] r2_c_raw;
  // [S2 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_last (.clock(clock), .rst_n(rst_n), .in_d(r1_last), .out_q(r2_last));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s1_s2_c_raw (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_c_raw), .out_q(r2_c_raw));
  // verilog_format: on

  // S3 C 原始编码，只在上一拍有效时保存。
  wire [`DP_FP32_W-1:0] r3_c_raw;
  // [S3 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_last (.clock(clock), .rst_n(rst_n), .in_d(r2_last), .out_q(r3_last));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s2_s3_c_raw (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_c_raw), .out_q(r3_c_raw));
  // verilog_format: on

  // S4 C 原始编码，只在上一拍有效时保存。
  wire [`DP_FP32_W-1:0] r4_c_raw;
  // [S4 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(r4_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_last (.clock(clock), .rst_n(rst_n), .in_d(r3_last), .out_q(r4_last));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s3_s4_c_raw (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_c_raw), .out_q(r4_c_raw));
  // verilog_format: on

  // S5 C 解包候选及对应寄存 token：符号、幅值、原始指数坐标、LZD 与特殊摘要。
  wire c_negative_d;
  wire [`DP_FP32_W-1:0] c_magnitude_d;
  wire signed [ANCHOR_W-1:0] c_anchor_d;
  wire [$clog2(`DP_FP32_W+1)-1:0] c_z_d;
  wire [`DP_SPECIAL_W-1:0] c_special_d;
  wire [`DP_SPECIAL_W-1:0] r5_c_special;
  wire r5_c_negative;
  wire [`DP_FP32_W-1:0] r5_c_magnitude;
  wire signed [ANCHOR_W-1:0] r5_c_anchor;
  wire [$clog2(`DP_FP32_W+1)-1:0] r5_c_z;
  // [S5 C 解包] 使用 r4_c_raw，而非当前 in_c，保证与五级前端同请求对齐。
  // C 的符号/幅值/anchor/z/特殊值在 S5 独立保存，随后与所有 group 一起参加 S6。
  dp_c_unpack #(
    .DETECT_LEADING_ZERO   ((QE_FRONTEND == 0) ? 1 : 0),
    .ANCHOR_W             (ANCHOR_W)
  ) u_c_unpack (
    .in_data              (r4_c_raw),
    .in_datatype          (1'b0),
    .out_negative         (c_negative_d),
    .out_magnitude        (c_magnitude_d),
    .out_anchor           (c_anchor_d),
    .out_z                (c_z_d),
    .out_special          (c_special_d)
  );

  // [S5 寄存边界] 捕获 C 解包 token 和请求旁带，供 S6 与 group token 一起对齐。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_valid (.clock(clock), .rst_n(rst_n), .in_d(r4_valid), .out_q(r5_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_last (.clock(clock), .rst_n(rst_n), .in_d(r4_last), .out_q(r5_last));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s4_s5_c_negative (.clock(clock), .in_en(rst_n & r4_valid), .in_d(c_negative_d), .out_q(r5_c_negative));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s4_s5_c_magnitude (.clock(clock), .in_en(rst_n & r4_valid), .in_d(c_magnitude_d), .out_q(r5_c_magnitude));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_c_anchor (.clock(clock), .in_en(rst_n & r4_valid), .in_d(c_anchor_d), .out_q(r5_c_anchor));
  dp_lib_DFFE #(.WIDTH($clog2(`DP_FP32_W + 1)))
  ff_s4_s5_c_z (.clock(clock), .in_en(rst_n & r4_valid), .in_d(c_z_d), .out_q(r5_c_z));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s4_s5_c_special (.clock(clock), .in_en(rst_n & r4_valid), .in_d(c_special_d), .out_q(r5_c_special));
  // verilog_format: on

  assign source_magnitude[GROUPS*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {
    r5_c_magnitude, {(GLOBAL_MAG_W - `DP_FP32_W) {1'b0}}
  };
  assign source_negative[GROUPS]                             = r5_c_negative;
  assign source_compare_exp[GROUPS*ANCHOR_W+:ANCHOR_W] = r5_c_anchor;
  assign source_anchor[GROUPS*ANCHOR_W+:ANCHOR_W]            = r5_c_anchor;
  assign source_z[GROUPS*Z_W+:Z_W]                           = (r5_c_z);
  assign source_special[GROUPS*`DP_SPECIAL_W+:`DP_SPECIAL_W] = r5_c_special;
  // S6 对齐候选/寄存值及 S7 旁带；anchor、负零和特殊摘要与叶子同拍。
  wire [SOURCE_COUNT*GLOBAL_W-1:0] leaves_d;
  wire [SOURCE_COUNT*GLOBAL_W-1:0] r6_leaves;
  wire signed [ANCHOR_W-1:0] common_d;
  wire signed [ANCHOR_W-1:0] r6_common;
  wire signed [ANCHOR_W-1:0] r7_common;
  wire negative_zero_d;
  wire r6_negative_zero;
  wire r7_negative_zero;
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] r6_special;
  wire [`DP_SPECIAL_W-1:0] r7_special;
  // [S6 全局对齐] 完整模块内完成有效源 MAX、净移位、恢复补码与特殊值归约。
  // leaves_d/common_d 等在 S6 DFF 同时捕获；不能将新 anchor 配给上一拍叶子。
  dp_global_align #(
    .PRECOMPUTED_EXPONENT (QE_FRONTEND),
    .N                    (SOURCE_COUNT),
    .MAG_W                (GLOBAL_MAG_W),
    .ANCHOR_W             (ANCHOR_W)
  ) u_global_alignment (
    .in_integer           (1'b0),
    .in_enable            (r5_valid),
    .in_magnitude         (source_magnitude),
    .in_anchor            (source_anchor),
    .in_compare_exp       (source_compare_exp),
    .in_z                 (source_z),
    .in_negative          (source_negative),
    .in_special           (source_special),
    .out_leaves           (leaves_d),
    .out_anchor           (common_d),
    .out_negative_zero    (negative_zero_d),
    .out_special          (special_d)
  );

  // [S6 寄存边界] 捕获全局对齐叶子、共同 anchor 和特殊/零符号旁带。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_valid (.clock(clock), .rst_n(rst_n), .in_d(r5_valid), .out_q(r6_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_last (.clock(clock), .rst_n(rst_n), .in_d(r5_last), .out_q(r6_last));
  dp_lib_DFFE #(.WIDTH(SOURCE_COUNT * GLOBAL_W))
  ff_s5_s6_leaves (.clock(clock), .in_en(rst_n & r5_valid), .in_d(leaves_d), .out_q(r6_leaves));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s5_s6_common_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(common_d), .out_q(r6_common));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s5_s6_negative_zero_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(negative_zero_d), .out_q(r6_negative_zero));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s5_s6_special_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(special_d), .out_q(r6_special));
  // verilog_format: on

  // S7 五项累加和：完整增长，不截断；数值坐标沿用 S6。
  wire signed [SUM_W-1:0] sum_d;
  wire signed [SUM_W-1:0] r7_sum;
  // [S7 最终累加树] 四个组结果加一份 C，共五项；没有基础/扩展分支旁路。
  // QE采用4:2+3:2+唯一CPA；E64 legacy保持原树。两者完整保留增长位。
  generate
    if (QE_FRONTEND != 0) begin : g_v19_sum
      dp_final_csa_sum #(
        .N(SOURCE_COUNT),
        .W(GLOBAL_W)
      ) u_final_sop_compress (
        .in_values(r6_leaves),
        .out_sum(sum_d)
      );
    end else begin : g_legacy_sum
  dp_sum_tree #(
    .N                    (SOURCE_COUNT),
    .W                    (GLOBAL_W)
  ) u_final_sop_tree (
    .in_values            (r6_leaves),
    .out_sum              (sum_d)
  );
    end
  endgenerate

  // [S7 寄存边界] 捕获最终累加和及旁带，供 S8 舍入/特殊值选择。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_valid (.clock(clock), .rst_n(rst_n), .in_d(r6_valid), .out_q(r7_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_last (.clock(clock), .rst_n(rst_n), .in_d(r6_last), .out_q(r7_last));
  dp_lib_DFFE #(.WIDTH(SUM_W))
  ff_s6_s7_sum (.clock(clock), .in_en(rst_n & r6_valid), .in_d(sum_d), .out_q(r7_sum));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s6_s7_common_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_common), .out_q(r7_common));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s6_s7_negative_zero_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_negative_zero), .out_q(r7_negative_zero));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s6_s7_special_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_special), .out_q(r7_special));
  // verilog_format: on

  // S8 有限 FP32 结果，后续特殊摘要优先覆盖。
  wire [`DP_FP32_W-1:0] finite_result;
  // [S8 有限结果转换] 对 S7 总和做 abs/LZD/归一化和唯一一次 FP32 RNE。
  // NaN/invalid/Inf 的最终选择在输出 DFF 输入完成，不在这里伪装成普通有限值。
  dp_fp32_round #(
    .SUM_W                (SUM_W),
    .ANCHOR_W             (ANCHOR_W),
    .GLOBAL_MAG_W         (GLOBAL_MAG_W)
  ) u_fp32_output (
    .in_sum               (r7_sum),
    .in_anchor            (r7_common),
    .in_negative_zero     (r7_negative_zero),
    .out_bits             (finite_result)
  );

  // [S8 输出选择] 组合数值选择在 DFF 外明确表达，寄存器只保存选定结果。
  wire [`DP_FP32_W-1:0] result_d;
  assign result_d = (r7_special[`DP_SP_NAN] | r7_special[`DP_SP_INVALID]) ?
    `DP_FP32_QNAN : (r7_special[`DP_SP_POS_INF] | r7_special[`DP_SP_NEG_INF]) ?
    (`DP_FP32_INF | {r7_special[`DP_SP_NEG_INF], {(`DP_FP32_W - 1) {1'b0}}}) : finite_result;

  // [S8 寄存边界] 捕获最终结果及 valid/last；L8/II=1，未新增寄存级。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_valid (.clock(clock), .rst_n(rst_n), .in_d(r7_valid), .out_q(r8_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_last (.clock(clock), .rst_n(rst_n), .in_d(r7_last), .out_q(r8_last));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s7_s8_out_d (.clock(clock), .in_en(rst_n & r7_valid), .in_d(result_d), .out_q(out_d));
  // verilog_format: on

  // Elaboration constraints are validation only; no synthesized datapath/reset.
  // synthesis translate_off
  initial begin
    if (K_FP16 != `DP_DEFAULT_K || GROUPS != `DP_DEFAULT_K / `DP_GROUP_H ||
        (QE_FRONTEND != 0 && QE_FRONTEND != 1)) begin
      $display("FAIL: %s", "fixed lowp profile requires K16, four groups and E/QE selection");
      $finish;
    end
    if (GROUPS != K_FP16 / `DP_GROUP_H) begin
      $display("FAIL: %s", "GROUPS is derived");
      $finish;
    end
    if (LOCAL_W < `DP_MIN_LOCAL_W) begin
      $display("FAIL: %s", "LOCAL_W requires at least F25");
      $finish;
    end
    if (GLOBAL_MAG_W < GROUP_MAG_W || GLOBAL_MAG_W < `DP_FP32_W) begin
      $display("FAIL: %s", "global window is smaller than source");
      $finish;
    end
  end
  // synthesis translate_on
endmodule
