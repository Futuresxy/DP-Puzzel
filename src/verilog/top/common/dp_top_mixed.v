`include "dp_defs.vh"
// Mixed HQE profiles: four multi groups plus two/four E or four QE groups.
// Atomic A/B/C input, per-request type, II=1, L=8, no output backpressure.
// At edge n input is accepted into S1; S8 updates at n+7, observed before n+8.
// Synchronous active-low reset cancels all valid tokens. Datapath holds in bubbles.
// LOCAL_W sets S3 amplitude and the downstream leaf/lane/group widths.
// GLOBAL_W sets S6 signed alignment and the floating F=GLOBAL_W-2.
// N=BASE_GROUPS+EXT_GROUPS+1 including C, L=ceil(log2(N)).
// S7 final SOP (TC).
// Precision / signal | S | I    | F
// ------------------ | - | ---- | -----------
// All floating modes | 1 | 1+L  | GLOBAL_W-2
// INT8 + INT32       | 1 | 32+L | GLOBAL_W-33
// S8 encodes FP32 with sign/exponent/fraction widths 1/8/23.
// S8 integer output (TC).
// Precision / signal | S | I  | F
// ------------------ | - | -- | -
// INT32              | 1 | 31 | 0
// 阅读顺序 / 功能边界：
// 前端 group 完成 S1-S5；C raw 经 S1-S4 透传，到 S5 才解包为同拍 token。
// S6 u_global_alignment -> S7 base/extension 子树与合并 -> S8 u_fp32_output。
// 按各级组合计算 -> ff_sN_sM_* 捕获 -> 下一级使用的顺序阅读。
// 基础组接收 req_fire；扩展组仅接收匹配 Q/E 类型的请求。外部只做一次原子握手。
module dp_top_mixed #(
  // 独立优化顶层启用：紧凑 QE 解包与扩展源浮点专用落位，基础组不变。
  parameter integer OPTIMIZE_QE = 0,
  // Q-only extension is static and leaves every existing profile unchanged.
  parameter integer EXT_Q_ONLY = 0,
  // 高精度基线并行度，混合顶层固定为 16。
  parameter integer K_FP16 = `DP_DEFAULT_K,
  // S3 局部幅值对齐窗口，改变时下游 lane/group 位宽同步推导。
  parameter integer LOCAL_W = `DP_DEFAULT_LOCAL_W,
  // S6 有符号对齐叶子位宽；含一个符号位。
  parameter integer GLOBAL_W = `DP_DEFAULT_GLOBAL_W,
  // Static extension capabilities; high-precision base capacity remains K_FP16=16.
  parameter integer EXT_GROUPS = 2,
  // 静态扩展能力：0 仅支持 E，1 支持 Q/E。
  parameter integer EXT_QE = 0,
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
  genvar group_index;
  // Extension request membership is pipelined independently of current input mode.
  wire extension_request;
  assign extension_request = (EXT_Q_ONLY != 0) ?
      ((in_a_datatype >= `DP_DT_MX8_E4M3) & (in_a_datatype <= `DP_DT_MX6_E2M3)) :
      (in_a_datatype >= ((EXT_QE != 0) ? `DP_DT_MX8_E4M3 : `DP_DT_MXFP4)) & (in_a_datatype <= `DP_DT_HIF4);


  `include "dp_functions.vh"
  // S5 两 lane 合并的补码总宽，较 lane 再增加一位。
  localparam integer GROUP_W = LOCAL_W + 1 + $clog2(`DP_Q_LANES) + $clog2(`DP_LANES);
  // S5 group 幅值容器宽度，不包含符号。
  localparam integer GROUP_MAG_W = GROUP_W - 1;
  // S6 幅值容器宽度，另加符号构成 GLOBAL_W。
  localparam integer GLOBAL_MAG_W = GLOBAL_W - 1;
  // 参与公共后端的物理源数：所有 group 加一次 C。
  localparam integer N = GROUPS + 1;
  // S7 完整规约宽度：GLOBAL_W+clog2(N)，不截断进位。
  localparam integer SUM_W = GLOBAL_W + $clog2(N);
  // 有符号指数坐标宽度，由合法幅值窗口推导。
  localparam integer ANCHOR_W = anchor_width(GLOBAL_MAG_W);
  // 共同幅值容器的前导零计数宽度。
  localparam integer Z_W = $clog2(GLOBAL_MAG_W + 1);
  // INT8 group 定点小数位数，仅用于恢复整数坐标。
  localparam integer INT_GROUP_F = GROUP_W - 1 - `DP_INT_PRODUCT_W - $clog2(`DP_Q_LANES);
  // INT32 在全局容器中的低位补零数。
  localparam integer INT_GLOBAL_F = GLOBAL_MAG_W - `DP_FP32_W;
  // [输入协议] 只有三路 valid 同时有效、datatype/scale 元组合法且 rst_n=1 才接收。
  // 缺一路只注入 bubble，不冻结已接收的事务；ready 表示本拍三路共同接收。
  wire tuple_legal;
  // verilog_format: off
  assign tuple_legal = (in_a_datatype <= `DP_DT_INT8) & (in_a_datatype == in_b_datatype) &
                       (in_c_datatype == (in_a_datatype == `DP_DT_INT8)) &
                       (in_scale_a_datatype == scale_type(in_a_datatype)) &
                       (in_scale_b_datatype == scale_type(in_a_datatype));
  // verilog_format: on
  wire req_fire;
  assign req_fire    = rst_n & in_a_valid & in_b_valid & in_c_valid & tuple_legal;
  assign out_a_ready = req_fire;
  assign out_b_ready = req_fire;
  assign out_c_ready = req_fire;
  // S1 request valid.
  wire r1_valid;
  // S2 request valid.
  wire r2_valid;
  // S3 request valid.
  wire r3_valid;
  // S4 request valid.
  wire r4_valid;
  // S5 request valid.
  wire r5_valid;
  // S6 request valid.
  wire r6_valid;
  // S7 request valid.
  wire r7_valid;
  // S8 request valid.
  wire r8_valid;
  // S1 request last.
  wire r1_last;
  // S2 request last.
  wire r2_last;
  // S3 request last.
  wire r3_last;
  // S4 request last.
  wire r4_last;
  // S5 request last.
  wire r5_last;
  // S6 request last.
  wire r6_last;
  // S7 request last.
  wire r7_last;
  // S8 request last.
  wire r8_last;
  // S1 request c_datatype.
  wire r1_c_datatype;
  // S2 request c_datatype.
  wire r2_c_datatype;
  // S3 request c_datatype.
  wire r3_c_datatype;
  // S4 request c_datatype.
  wire r4_c_datatype;
  // S5 request c_datatype.
  wire r5_c_datatype;
  // S6 request c_datatype.
  wire r6_c_datatype;
  // S7 request c_datatype.
  wire r7_c_datatype;
  // S8 request c_datatype.
  wire r8_c_datatype;
  // S1 request c_raw.
  wire [`DP_FP32_W-1:0] r1_c_raw;
  // S2 request c_raw.
  wire [`DP_FP32_W-1:0] r2_c_raw;
  // S3 request c_raw.
  wire [`DP_FP32_W-1:0] r3_c_raw;
  // S4 request c_raw.
  wire [`DP_FP32_W-1:0] r4_c_raw;
  assign out_valid      = r8_valid;
  assign out_last       = r8_last & out_valid;
  assign out_d_datatype = r8_c_datatype;
  // [S1-S5 group 前端] G=K_FP16/4，每 group 消费两个连续 32 位 lane。
  // K16 时为四个 group；source 槽 0..G-1 放组结果，槽 G 放 C。
  // 低位补零将各来源幅值放入 GLOBAL_MAG_W；不是新增有效精度或动态移位。
  wire [N*GLOBAL_MAG_W-1:0] source_magnitude;
  wire [N*ANCHOR_W-1:0] source_anchor;
  // S5预计算 e，仅用于MAX；移位差仍用A_raw。
  wire [N*ANCHOR_W-1:0] source_compare_exp;
  wire [N*Z_W-1:0] source_z;
  wire [N-1:0] source_negative;
  wire [N*`DP_SPECIAL_W-1:0] source_special;
  generate
    for (group_index = 0; group_index < GROUPS; group_index = group_index + 1) begin : g_group
      wire [GROUP_MAG_W-1:0] group_align_magnitude;
      wire signed [ANCHOR_W-1:0] group_align_anchor;
      wire signed [ANCHOR_W-1:0] group_align_compare_exp;
      wire [$clog2(GROUP_MAG_W+1)-1:0] group_align_leading_zero_count;
      wire group_align_negative;
      wire group_top_valid;
      wire [`DP_SPECIAL_W-1:0] group_align_special;
      if (group_index < BASE_GROUPS) begin : g_base
        dp_group #(
            .BASELINE_V18(1),
            .LOCAL_W (LOCAL_W),
            .ANCHOR_W(ANCHOR_W)
        ) u_group_unit (
            .clock            (clock),
            .rst_n            (rst_n),
            .in_valid         (req_fire),
            .in_datatype      (in_a_datatype),
            .in_a             (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_b             (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_scale_a       (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_b       (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_datatype(in_scale_a_datatype),
            .in_e1_a          (in_hif4_e1_a[group_index*4+:4]),
            .in_e1_b          (in_hif4_e1_b[group_index*4+:4]),
            .in_e2_a          (in_hif4_e2_a[group_index*2+:2]),
            .in_e2_b          (in_hif4_e2_b[group_index*2+:2]),
            .out_valid        (group_top_valid),
            .out_negative     (group_align_negative),
            .out_magnitude    (group_align_magnitude),
            .out_anchor       (group_align_anchor),
            .out_compare_exp  (group_align_compare_exp),
            .out_z            (group_align_leading_zero_count),
            .out_special      (group_align_special)
        );
      end else if (EXT_Q_ONLY != 0) begin : g_q
        dp_group_q #(
            .LOCAL_W (LOCAL_W),
            .ANCHOR_W(ANCHOR_W)
        ) u_group_unit (
            .clock            (clock),
            .rst_n            (rst_n),
            .in_valid         (req_fire & extension_request),
            .in_datatype      (in_a_datatype),
            .in_a             (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_b             (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_scale_a       (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_b       (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .out_valid        (group_top_valid),
            .out_negative     (group_align_negative),
            .out_magnitude    (group_align_magnitude),
            .out_anchor       (group_align_anchor),
            .out_compare_exp  (group_align_compare_exp),
            .out_z            (group_align_leading_zero_count),
            .out_special      (group_align_special)
        );
      end else if (EXT_QE != 0) begin : g_qe
        dp_group_qe #(
            .ARCHITECTURE_V19(1),
            .COMPACT_UNPACK(OPTIMIZE_QE),
            .LOCAL_W (LOCAL_W),
            .ANCHOR_W(ANCHOR_W)
        ) u_group_unit (
            .clock            (clock),
            .rst_n            (rst_n),
            .in_valid         (req_fire & extension_request),
            .in_datatype      (in_a_datatype),
            .in_a             (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_b             (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_scale_a       (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_b       (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_datatype(in_scale_a_datatype),
            .in_e1_a          (in_hif4_e1_a[group_index*4+:4]),
            .in_e1_b          (in_hif4_e1_b[group_index*4+:4]),
            .in_e2_a          (in_hif4_e2_a[group_index*2+:2]),
            .in_e2_b          (in_hif4_e2_b[group_index*2+:2]),
            .out_valid        (group_top_valid),
            .out_negative     (group_align_negative),
            .out_magnitude    (group_align_magnitude),
            .out_anchor       (group_align_anchor),
            .out_compare_exp  (group_align_compare_exp),
            .out_z            (group_align_leading_zero_count),
            .out_special      (group_align_special)
        );
      end else begin : g_e
        dp_group_e #(
            .ARCHITECTURE_V19(1),
            .LOCAL_W (LOCAL_W),
            .ANCHOR_W(ANCHOR_W)
        ) u_group_unit (
            .clock            (clock),
            .rst_n            (rst_n),
            .in_valid         (req_fire & extension_request),
            .in_datatype      (in_a_datatype),
            .in_a             (in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_b             (in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
            .in_scale_a       (in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_b       (in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
            .in_scale_datatype(in_scale_a_datatype),
            .in_e1_a          (in_hif4_e1_a[group_index*4+:4]),
            .in_e1_b          (in_hif4_e1_b[group_index*4+:4]),
            .in_e2_a          (in_hif4_e2_a[group_index*2+:2]),
            .in_e2_b          (in_hif4_e2_b[group_index*2+:2]),
            .out_valid        (group_top_valid),
            .out_negative     (group_align_negative),
            .out_magnitude    (group_align_magnitude),
            .out_anchor       (group_align_anchor),
            .out_compare_exp  (group_align_compare_exp),
            .out_z            (group_align_leading_zero_count),
            .out_special      (group_align_special)
        );
      end
      if (group_index >= BASE_GROUPS) begin : g_float_extension_layout
        // 扩展组从不参与整数请求；只补浮点低零，参与掩码仍在后端生效。
        assign source_magnitude[group_index*GLOBAL_MAG_W+:GLOBAL_MAG_W] =
            {group_align_magnitude, {(GLOBAL_MAG_W-GROUP_MAG_W){1'b0}}};
      end else begin : g_reference_layout
        assign source_magnitude[group_index*GLOBAL_MAG_W+:GLOBAL_MAG_W] = r5_c_datatype ?
          (({{(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}, group_align_magnitude} >> INT_GROUP_F) <<
           INT_GLOBAL_F) : {group_align_magnitude, {(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}};
      end
      assign source_negative[group_index] = group_align_negative;
      assign source_anchor[group_index*ANCHOR_W+:ANCHOR_W] = group_align_anchor;
      assign source_compare_exp[group_index*ANCHOR_W+:ANCHOR_W] = group_align_compare_exp;
      assign source_z[group_index*Z_W+:Z_W] = {
        {(Z_W - $clog2(GROUP_MAG_W + 1)) {1'b0}}, group_align_leading_zero_count
      };
      assign source_special[group_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] = group_align_special;
    end
  endgenerate
  // [S1-S4 C/控制传递] group 内执行前端计算；本层同拍传递 C 和请求旁带。

  // [S1 寄存边界] 保存 C 原始编码和 valid/last/类型，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(req_fire), .out_q(r1_valid));
  // S1 membership belongs to this request, not the current input datatype.
  wire r1_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_extension (.clock(clock), .rst_n(rst_n), .in_d(req_fire & extension_request), .out_q(r1_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_last (.clock(clock), .rst_n(rst_n), .in_d(req_fire & in_last), .out_q(r1_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s0_s1_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(req_fire), .in_d(in_c_datatype), .out_q(r1_c_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s0_s1_c_raw (.clock(clock), .in_en(rst_n & req_fire), .in_d(in_c), .out_q(r1_c_raw));
  // verilog_format: on

  // [S2 寄存边界] 保存 C 原始编码和 valid/last/类型，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(r1_valid), .out_q(r2_valid));
  // S2 membership belongs to this request, not the current input datatype.
  wire r2_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_extension (.clock(clock), .rst_n(rst_n), .in_d(r1_extension), .out_q(r2_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_last (.clock(clock), .rst_n(rst_n), .in_d(r1_last), .out_q(r2_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s1_s2_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r1_valid), .in_d(r1_c_datatype), .out_q(r2_c_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s1_s2_c_raw (.clock(clock), .in_en(rst_n & r1_valid), .in_d(r1_c_raw), .out_q(r2_c_raw));
  // verilog_format: on

  // [S3 寄存边界] 保存 C 原始编码和 valid/last/类型，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(r2_valid), .out_q(r3_valid));
  // S3 membership belongs to this request, not the current input datatype.
  wire r3_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_extension (.clock(clock), .rst_n(rst_n), .in_d(r2_extension), .out_q(r3_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_last (.clock(clock), .rst_n(rst_n), .in_d(r2_last), .out_q(r3_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s2_s3_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r2_valid), .in_d(r2_c_datatype), .out_q(r3_c_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s2_s3_c_raw (.clock(clock), .in_en(rst_n & r2_valid), .in_d(r2_c_raw), .out_q(r3_c_raw));
  // verilog_format: on

  // [S4 寄存边界] 保存 C 原始编码和 valid/last/类型，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(r3_valid), .out_q(r4_valid));
  // S4 membership belongs to this request, not the current input datatype.
  wire r4_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_extension (.clock(clock), .rst_n(rst_n), .in_d(r3_extension), .out_q(r4_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_last (.clock(clock), .rst_n(rst_n), .in_d(r3_last), .out_q(r4_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s3_s4_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r3_valid), .in_d(r3_c_datatype), .out_q(r4_c_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s3_s4_c_raw (.clock(clock), .in_en(rst_n & r3_valid), .in_d(r3_c_raw), .out_q(r4_c_raw));
  // verilog_format: on

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
      .DETECT_LEADING_ZERO(0),
      .ANCHOR_W(ANCHOR_W)
  ) u_c_unpack (
      .in_data      (r4_c_raw),
      .in_datatype  (r4_c_datatype),
      .out_negative (c_negative_d),
      .out_magnitude(c_magnitude_d),
      .out_anchor   (c_anchor_d),
      .out_z        (c_z_d),
      .out_special  (c_special_d)
  );

  // [S5 寄存边界] 捕获 C 解包 token 和请求旁带，供 S6 与 group token 一起对齐。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_valid (.clock(clock), .rst_n(rst_n), .in_d(r4_valid), .out_q(r5_valid));
  // S5 membership belongs to this request, not the current input datatype.
  wire r5_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_extension (.clock(clock), .rst_n(rst_n), .in_d(r4_extension), .out_q(r5_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_last (.clock(clock), .rst_n(rst_n), .in_d(r4_last), .out_q(r5_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s4_s5_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r4_valid), .in_d(r4_c_datatype), .out_q(r5_c_datatype));
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

  assign source_magnitude[GROUPS*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {r5_c_magnitude, {(GLOBAL_MAG_W - `DP_FP32_W) {1'b0}}};
  assign source_negative[GROUPS]                             = r5_c_negative;
  assign source_compare_exp[GROUPS*ANCHOR_W+:ANCHOR_W] = r5_c_anchor;
  assign source_anchor[GROUPS*ANCHOR_W+:ANCHOR_W]            = r5_c_anchor;
  assign source_z[GROUPS*Z_W+:Z_W]                           = (r5_c_z);
  assign source_special[GROUPS*`DP_SPECIAL_W+:`DP_SPECIAL_W] = r5_c_special;
  wire [N*GLOBAL_W-1:0] leaves_d;
  wire [N*GLOBAL_W-1:0] r6_leaves;
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
  dp_mixed_global_align #(
      .PRECOMPUTED_COMPARE(1),
      .FLOAT_ONLY_EXTENSION(1),
      .BASE_GROUPS(BASE_GROUPS),
      .EXT_GROUPS (EXT_GROUPS),
      .N          (N),
      .MAG_W      (GLOBAL_MAG_W),
      .ANCHOR_W   (ANCHOR_W)
  ) u_global_alignment (
      .in_participate   ({1'b1, {EXT_GROUPS{r5_extension}}, {BASE_GROUPS{1'b1}}}),
      .in_integer       (r5_c_datatype),
      .in_enable        (r5_valid),
      .in_magnitude     (source_magnitude),
      .in_anchor        (source_anchor),
      .in_compare_exp   (source_compare_exp),
      .in_z             (source_z),
      .in_negative      (source_negative),
      .in_special       (source_special),
      .out_leaves       (leaves_d),
      .out_anchor       (common_d),
      .out_negative_zero(negative_zero_d),
      .out_special      (special_d)
  );

  // [S6 寄存边界] 捕获全局对齐叶子、共同 anchor 和特殊/零符号旁带。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_valid (.clock(clock), .rst_n(rst_n), .in_d(r5_valid), .out_q(r6_valid));
  // S6 membership belongs to this request, not the current input datatype.
  wire r6_extension;
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_extension (.clock(clock), .rst_n(rst_n), .in_d(r5_extension), .out_q(r6_extension));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_last (.clock(clock), .rst_n(rst_n), .in_d(r5_last), .out_q(r6_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s5_s6_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r5_valid), .in_d(r5_c_datatype), .out_q(r6_c_datatype));
  dp_lib_DFFE #(.WIDTH(BASE_GROUPS * GLOBAL_W))
  ff_s5_s6_base_leaves (.clock(clock), .in_en(rst_n & r5_valid), .in_d(leaves_d[0+:BASE_GROUPS*GLOBAL_W]), .out_q(r6_leaves[0+:BASE_GROUPS*GLOBAL_W]));
  dp_lib_DFFE #(.WIDTH(GLOBAL_W))
  ff_s5_s6_c_leaf (.clock(clock), .in_en(rst_n & r5_valid), .in_d(leaves_d[GROUPS*GLOBAL_W+:GLOBAL_W]), .out_q(r6_leaves[GROUPS*GLOBAL_W+:GLOBAL_W]));
  // 扩展寄存器在高精度请求保持；消费端按同拍membership显式恢复零。
  wire [EXT_GROUPS*GLOBAL_W-1:0] r6_extension_leaves;
  dp_lib_DFFE #(.WIDTH(EXT_GROUPS * GLOBAL_W))
  ff_s5_s6_extension_leaves (.clock(clock), .in_en(rst_n & r5_valid & r5_extension), .in_d(leaves_d[BASE_GROUPS*GLOBAL_W+:EXT_GROUPS*GLOBAL_W]), .out_q(r6_extension_leaves));
  assign r6_leaves[BASE_GROUPS*GLOBAL_W+:EXT_GROUPS*GLOBAL_W] = r6_extension ? r6_extension_leaves : 0;
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s5_s6_common_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(common_d), .out_q(r6_common));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s5_s6_negative_zero_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(negative_zero_d), .out_q(r6_negative_zero));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s5_s6_special_s6 (.clock(clock), .in_en(rst_n & r5_valid), .in_d(special_d), .out_q(r6_special));
  // verilog_format: on

  wire signed [SUM_W-1:0] sum_d;
  wire signed [SUM_W-1:0] r7_sum;
  // [S7 carry-save规约] 基础4组+C与扩展2/4组保持两行，经双行MUX后唯一CPA。
  // E96为S43，E128/Q64E128为S44；含符号增长位完整保留。
  dp_mixed_csa_sum #(
      .EXT_GROUPS(EXT_GROUPS),
      .W         (GLOBAL_W),
      .SUM_W     (SUM_W)
  ) u_final_sop_compress (
      .in_extension_active(r6_extension),
      .in_values          (r6_leaves),
      .out_sum            (sum_d)
  );

  // [S7 寄存边界] 捕获最终累加和及旁带，供 S8 舍入/特殊值选择。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_valid (.clock(clock), .rst_n(rst_n), .in_d(r6_valid), .out_q(r7_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_last (.clock(clock), .rst_n(rst_n), .in_d(r6_last), .out_q(r7_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s6_s7_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r6_valid), .in_d(r6_c_datatype), .out_q(r7_c_datatype));
  dp_lib_DFFE #(.WIDTH(SUM_W))
  ff_s6_s7_sum (.clock(clock), .in_en(rst_n & r6_valid), .in_d(sum_d), .out_q(r7_sum));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s6_s7_common_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_common), .out_q(r7_common));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s6_s7_negative_zero_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_negative_zero), .out_q(r7_negative_zero));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s6_s7_special_s7 (.clock(clock), .in_en(rst_n & r6_valid), .in_d(r6_special), .out_q(r7_special));
  // verilog_format: on

  wire [`DP_FP32_W-1:0] finite_result;
  // Isolate S8 floating arithmetic for integer requests.
  wire signed [SUM_W-1:0] float_sum;
  assign float_sum = r7_c_datatype ? 0 : r7_sum;
  // [S8 有限结果转换] 对 S7 总和做 abs/LZD/归一化和唯一一次 FP32 RNE。
  // NaN/invalid/Inf 的最终选择在输出 DFF 输入完成，不在这里伪装成普通有限值。
  dp_fp32_round #(
      .SUM_W       (SUM_W),
      .ANCHOR_W    (ANCHOR_W),
      .GLOBAL_MAG_W(GLOBAL_MAG_W)
  ) u_fp32_output (
      .in_sum          (float_sum),
      .in_anchor       (r7_common),
      .in_negative_zero(r7_negative_zero),
      .out_bits        (finite_result)
  );

  // [S8 输出选择] 组合数值选择在 DFF 外明确表达，寄存器只保存选定结果。
  wire [`DP_FP32_W-1:0] result_s8_d;
  assign result_s8_d = r7_c_datatype ?
    r7_sum[INT_GLOBAL_F+:`DP_FP32_W] : (r7_special[`DP_SP_NAN] | r7_special[`DP_SP_INVALID]) ?
    `DP_FP32_QNAN : (r7_special[`DP_SP_POS_INF] | r7_special[`DP_SP_NEG_INF]) ?
    (`DP_FP32_INF | {r7_special[`DP_SP_NEG_INF], {(`DP_FP32_W - 1) {1'b0}}}) : finite_result;

  // [S8 寄存边界] 捕获最终结果及 valid/last；L8/II=1，未新增寄存级。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_valid (.clock(clock), .rst_n(rst_n), .in_d(r7_valid), .out_q(r8_valid));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_last (.clock(clock), .rst_n(rst_n), .in_d(r7_last), .out_q(r8_last));
  dp_lib_DFFRE #(.WIDTH(1))
  ff_s7_s8_c_datatype (.clock(clock), .rst_n(rst_n), .in_en(r7_valid), .in_d(r7_c_datatype), .out_q(r8_c_datatype));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s7_s8_out_d (.clock(clock), .in_en(rst_n & r7_valid), .in_d(result_s8_d), .out_q(out_d));
  // verilog_format: on

  // Elaboration constraints are validation only; no synthesized datapath/reset.
  // synthesis translate_off
  initial begin
    if (K_FP16 != `DP_DEFAULT_K) begin
      $display("FAIL: %s", "mixed base K_FP16 must remain 16");
      $finish;
    end
    if ((GROUPS != BASE_GROUPS+EXT_GROUPS) || (BASE_GROUPS != `DP_DEFAULT_K/`DP_GROUP_H) || (EXT_GROUPS != 2 && EXT_GROUPS != 4)) begin
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
