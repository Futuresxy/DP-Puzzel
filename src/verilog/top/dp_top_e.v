`include "dp_defs.vh"
// E-only single DP: MXFP4/NVFP4/HiF4, E64 at K_FP16=16.
// K_FP16 is a compatibility size index: K_E=4*K_FP16, groups=K_FP16/4.
// Atomic A/B/C input, per-request type, II=1, L=8, no output backpressure.
// At edge n input is accepted into S1; S8 updates at n+7, observed before n+8.
// Synchronous active-low reset cancels all valid tokens. Datapath holds in bubbles.
// LOCAL_W sets the compatible S5 token slot (M=LOCAL_W+3); E internals stay narrow.
// GLOBAL_W sets S6 signed alignment and the floating F=GLOBAL_W-2.
// K=K_FP16, N=K/4+1 including C, L=ceil(log2(N)).
// S7 final SOP (TC).
// Precision / signal | S | I    | F
// ------------------ | - | ---- | -----------
// All floating modes | 1 | 1+L  | GLOBAL_W-2
// S8 encodes FP32 with sign/exponent/fraction widths 1/8/23.
// 阅读顺序 / 功能边界：
// 前端 group 完成 S1-S5；C raw 经 S1-S4 透传，到 S5 才解包为同拍 token。
// S6 u_global_alignment -> S7 u_final_sop_tree -> S8 u_fp32_output/特殊值选择。
// 按各级组合计算 -> ff_sN_sM_* 捕获 -> 下一级使用的顺序阅读。
// 所有 group 同步接收一个 req_fire，外部仅一次原子 A/B/C 握手，无输出反压。
module dp_top_e #(
  parameter integer K_FP16   = `DP_DEFAULT_K,
  parameter integer LOCAL_W  = `DP_DEFAULT_LOCAL_W,
  parameter integer GLOBAL_W = `DP_DEFAULT_GLOBAL_W,
  parameter integer GROUPS   = K_FP16 /`DP_GROUP_H
) (
  input wire clock,
  input wire rst_n,
  input wire in_a_valid,
  input wire in_b_valid,
  input wire in_c_valid,
  output wire out_a_ready,
  output wire out_b_ready,
  output wire out_c_ready,
  input wire [K_FP16*`DP_HALF_W-1:0] in_a,
  input wire [K_FP16*`DP_HALF_W-1:0] in_b,
  input wire [`DP_TYPE_W-1:0] in_a_datatype,
  input wire [`DP_TYPE_W-1:0] in_b_datatype,
  input wire [GROUPS*`DP_SCALE_W-1:0] in_scale_a,
  input wire [GROUPS*`DP_SCALE_W-1:0] in_scale_b,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_a_datatype,
  input wire [`DP_SCALE_TYPE_W-1:0] in_scale_b_datatype,
  input wire [GROUPS*4-1:0] in_hif4_e1_a,
  input wire [GROUPS*4-1:0] in_hif4_e1_b,
  input wire [GROUPS*2-1:0] in_hif4_e2_a,
  input wire [GROUPS*2-1:0] in_hif4_e2_b,
  input wire [`DP_FP32_W-1:0] in_c,
  input wire in_c_datatype,
  input wire in_last,
  output wire out_valid,
  output wire [`DP_FP32_W-1:0] out_d,
  output wire out_d_datatype,
  output wire out_last
);
  genvar group_index;

  `include "dp_functions.vh"
  localparam integer GROUP_MAG_W = LOCAL_W + 3;
  localparam integer GLOBAL_MAG_W = GLOBAL_W - 1;
  localparam integer N = GROUPS + 1;
  localparam integer SUM_W = GLOBAL_W + $clog2(N);
  localparam integer ANCHOR_W = anchor_width(GLOBAL_MAG_W);
  localparam integer Z_W = $clog2(GLOBAL_MAG_W + 1);
  // [输入协议] 只有三路 valid 同时有效、datatype/scale 元组合法且 rst_n=1 才接收。
  // 缺一路只注入 bubble，不冻结已接收的事务；ready 表示本拍三路共同接收。
  wire tuple_legal;
  assign tuple_legal = (in_a_datatype == `DP_DT_MXFP4 | in_a_datatype == `DP_DT_NVFP4 |
                        in_a_datatype == `DP_DT_HIF4) &
    in_a_datatype == in_b_datatype & ~in_c_datatype & in_scale_a_datatype == scale_type(
    in_a_datatype
  ) & in_scale_b_datatype == scale_type(
    in_a_datatype
  );
  wire req_fire;
  assign req_fire = rst_n & in_a_valid & in_b_valid & in_c_valid & tuple_legal;
  assign out_a_ready = req_fire;
  assign out_b_ready = req_fire;
  assign out_c_ready = req_fire;
  wire [`DP_BASE_LATENCY-1:0] valid_q;
  wire [`DP_BASE_LATENCY-1:0] last_q;
  wire [`DP_FP32_W-1:0] c_raw_q[0:3];
  assign out_valid = valid_q[`DP_BASE_LATENCY-1];
  assign out_last = last_q[`DP_BASE_LATENCY-1] & out_valid;
  assign out_d_datatype = 1'b0;
  // [S1-S5 group 前端] G=K_FP16/4，每 group 消费两个连续 32 位 lane。
  // K16 时为四个 group；source 槽 0..G-1 放组结果，槽 G 放 C。
  // 低位补零将各来源幅值放入 GLOBAL_MAG_W；不是新增有效精度或动态移位。
  wire [N*GLOBAL_MAG_W-1:0] source_magnitude;
  wire [N*ANCHOR_W-1:0] source_anchor;
  wire [N*Z_W-1:0] source_z;
  wire [N-1:0] source_negative;
  wire [N*`DP_SPECIAL_W-1:0] source_special;
  generate
    for (group_index = 0; group_index < GROUPS; group_index = group_index + 1) begin : g_group
      wire [GROUP_MAG_W-1:0] group_align_magnitude;
      wire signed [ANCHOR_W-1:0] group_align_anchor;
      wire signed [ANCHOR_W-1:0] unused_compare_exp;
      wire [$clog2(GROUP_MAG_W+1)-1:0] group_align_leading_zero_count;
      wire group_align_negative;
      wire group_top_valid;
      wire [`DP_SPECIAL_W-1:0] group_align_special;
      dp_group_e #(
        .LOCAL_W (LOCAL_W),
        .ANCHOR_W(ANCHOR_W)
      ) u_group_unit (
        .clock(clock),
        .rst_n(rst_n),
        .in_valid(req_fire),
        .in_datatype(in_a_datatype),
        .in_a(in_a[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
        .in_b(in_b[group_index*`DP_LANES*`DP_LANE_W+:`DP_LANES*`DP_LANE_W]),
        .in_scale_a(in_scale_a[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
        .in_scale_b(in_scale_b[group_index*`DP_SCALE_W+:`DP_SCALE_W]),
        .in_scale_datatype(in_scale_a_datatype),
        .in_e1_a(in_hif4_e1_a[group_index*4+:4]),
        .in_e1_b(in_hif4_e1_b[group_index*4+:4]),
        .in_e2_a(in_hif4_e2_a[group_index*2+:2]),
        .in_e2_b(in_hif4_e2_b[group_index*2+:2]),
        .out_valid(group_top_valid),
        .out_negative(group_align_negative),
        .out_magnitude(group_align_magnitude),
        .out_anchor(group_align_anchor),
        .out_compare_exp(unused_compare_exp),
        .out_z(group_align_leading_zero_count),
        .out_special(group_align_special)
      );
      assign source_magnitude[group_index*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {
        group_align_magnitude, {(GLOBAL_MAG_W - GROUP_MAG_W) {1'b0}}
      };
      assign source_negative[group_index] = group_align_negative;
      assign source_anchor[group_index*ANCHOR_W+:ANCHOR_W] = group_align_anchor;
      assign source_z[group_index*Z_W+:Z_W] = {
        {(Z_W - $clog2(GROUP_MAG_W + 1)) {1'b0}}, group_align_leading_zero_count
      };
      assign source_special[group_index*`DP_SPECIAL_W+:`DP_SPECIAL_W] = group_align_special;
    end
  endgenerate
  // [S1-S4 C/控制传递] group 内执行前端计算；本层同拍传递 C 和请求旁带。

  // [S1 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_valid (.clock(clock), .rst_n(rst_n), .in_d(req_fire), .out_q(valid_q[0]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s0_s1_last (.clock(clock), .rst_n(rst_n), .in_d(req_fire & in_last), .out_q(last_q[0]));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s0_s1_c_raw (.clock(clock), .in_en(rst_n & req_fire), .in_d(in_c), .out_q(c_raw_q[0]));
  // verilog_format: on

  // [S2 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[0]), .out_q(valid_q[1]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s1_s2_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[0]), .out_q(last_q[1]));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s1_s2_c_raw (.clock(clock), .in_en(rst_n & valid_q[0]), .in_d(c_raw_q[0]), .out_q(c_raw_q[1]));
  // verilog_format: on

  // [S3 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[1]), .out_q(valid_q[2]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s2_s3_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[1]), .out_q(last_q[2]));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s2_s3_c_raw (.clock(clock), .in_en(rst_n & valid_q[1]), .in_d(c_raw_q[1]), .out_q(c_raw_q[2]));
  // verilog_format: on

  // [S4 寄存边界] 保存 C 原始编码和 valid/last，与前端同级数据同步推进。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[2]), .out_q(valid_q[3]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s3_s4_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[2]), .out_q(last_q[3]));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s3_s4_c_raw (.clock(clock), .in_en(rst_n & valid_q[2]), .in_d(c_raw_q[2]), .out_q(c_raw_q[3]));
  // verilog_format: on

  wire c_negative_d;
  wire [`DP_FP32_W-1:0] c_magnitude_d;
  wire signed [ANCHOR_W-1:0] c_anchor_d;
  wire [$clog2(`DP_FP32_W+1)-1:0] c_z_d;
  wire [`DP_SPECIAL_W-1:0] c_special_d;
  wire [`DP_SPECIAL_W-1:0] c_special_q;
  wire c_negative_q;
  wire [`DP_FP32_W-1:0] c_magnitude_q;
  wire signed [ANCHOR_W-1:0] c_anchor_q;
  wire [$clog2(`DP_FP32_W+1)-1:0] c_z_q;
  // [S5 C 解包] 使用 c_raw_q[3]，而非当前 in_c，保证与五级前端同请求对齐。
  // C 的符号/幅值/anchor/z/特殊值在 S5 独立保存，随后与所有 group 一起参加 S6。
  dp_c_unpack #(
    .ANCHOR_W(ANCHOR_W)
  ) u_c_unpack (
    .in_data(c_raw_q[3]),
    .in_datatype(1'b0),
    .out_negative(c_negative_d),
    .out_magnitude(c_magnitude_d),
    .out_anchor(c_anchor_d),
    .out_z(c_z_d),
    .out_special(c_special_d)
  );

  // [S5 寄存边界] 捕获 C 解包 token 和请求旁带，供 S6 与 group token 一起对齐。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[3]), .out_q(valid_q[4]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s4_s5_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[3]), .out_q(last_q[4]));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s4_s5_c_negative (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(c_negative_d), .out_q(c_negative_q));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s4_s5_c_magnitude (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(c_magnitude_d), .out_q(c_magnitude_q));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s4_s5_c_anchor (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(c_anchor_d), .out_q(c_anchor_q));
  dp_lib_DFFE #(.WIDTH($clog2(`DP_FP32_W + 1)))
  ff_s4_s5_c_z (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(c_z_d), .out_q(c_z_q));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s4_s5_c_special (.clock(clock), .in_en(rst_n & valid_q[3]), .in_d(c_special_d), .out_q(c_special_q));
  // verilog_format: on

  assign source_magnitude[GROUPS*GLOBAL_MAG_W+:GLOBAL_MAG_W] = {
    c_magnitude_q, {(GLOBAL_MAG_W - `DP_FP32_W) {1'b0}}
  };
  assign source_negative[GROUPS] = c_negative_q;
  assign source_anchor[GROUPS*ANCHOR_W+:ANCHOR_W] = c_anchor_q;
  assign source_z[GROUPS*Z_W+:Z_W] = (c_z_q);
  assign source_special[GROUPS*`DP_SPECIAL_W+:`DP_SPECIAL_W] = c_special_q;
  wire [N*GLOBAL_W-1:0] leaves_d;
  wire [N*GLOBAL_W-1:0] leaves_q;
  wire signed [ANCHOR_W-1:0] common_d;
  wire signed [ANCHOR_W-1:0] common_s6_q;
  wire signed [ANCHOR_W-1:0] common_s7_q;
  wire negative_zero_d;
  wire negative_zero_s6_q;
  wire negative_zero_s7_q;
  wire [`DP_SPECIAL_W-1:0] special_d;
  wire [`DP_SPECIAL_W-1:0] special_s6_q;
  wire [`DP_SPECIAL_W-1:0] special_s7_q;
  // [S6 全局对齐] 完整模块内完成有效源 MAX、净移位、恢复补码与特殊值归约。
  // leaves_d/common_d 等在 S6 DFF 同时捕获；不能将新 anchor 配给上一拍叶子。
  dp_global_align #(
    .N(N),
    .MAG_W(GLOBAL_MAG_W),
    .ANCHOR_W(ANCHOR_W)
  ) u_global_alignment (
    .in_integer(1'b0),
    .in_enable(valid_q[4]),
    .in_magnitude(source_magnitude),
    .in_anchor(source_anchor),
    .in_compare_exp({N*ANCHOR_W{1'b0}}),
    .in_z(source_z),
    .in_negative(source_negative),
    .in_special(source_special),
    .out_leaves(leaves_d),
    .out_anchor(common_d),
    .out_negative_zero(negative_zero_d),
    .out_special(special_d)
  );

  // [S6 寄存边界] 捕获全局对齐叶子、共同 anchor 和特殊/零符号旁带。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[4]), .out_q(valid_q[5]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s5_s6_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[4]), .out_q(last_q[5]));
  dp_lib_DFFE #(.WIDTH(N * GLOBAL_W))
  ff_s5_s6_leaves (.clock(clock), .in_en(rst_n & valid_q[4]), .in_d(leaves_d), .out_q(leaves_q));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s5_s6_common_s6 (.clock(clock), .in_en(rst_n & valid_q[4]), .in_d(common_d), .out_q(common_s6_q));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s5_s6_negative_zero_s6 (.clock(clock), .in_en(rst_n & valid_q[4]), .in_d(negative_zero_d), .out_q(negative_zero_s6_q));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s5_s6_special_s6 (.clock(clock), .in_en(rst_n & valid_q[4]), .in_d(special_d), .out_q(special_s6_q));
  // verilog_format: on

  wire signed [SUM_W-1:0] sum_d;
  wire signed [SUM_W-1:0] sum_q;
  // [S7 最终累加树] G 个组结果加 C，共 G+1 项；K4/K8/K16 对应 2/3/5 项。
  // 平衡树保留 ceil(log2(G+1)) 个增长位，小数位数及 common anchor 不改变。
  dp_sum_tree #(
    .N(N),
    .W(GLOBAL_W)
  ) u_final_sop_tree (
    .in_values(leaves_q),
    .out_sum  (sum_d)
  );

  // [S7 寄存边界] 捕获最终累加和及旁带，供 S8 舍入/特殊值选择。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[5]), .out_q(valid_q[6]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s6_s7_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[5]), .out_q(last_q[6]));
  dp_lib_DFFE #(.WIDTH(SUM_W))
  ff_s6_s7_sum (.clock(clock), .in_en(rst_n & valid_q[5]), .in_d(sum_d), .out_q(sum_q));
  dp_lib_DFFE #(.WIDTH(ANCHOR_W))
  ff_s6_s7_common_s7 (.clock(clock), .in_en(rst_n & valid_q[5]), .in_d(common_s6_q), .out_q(common_s7_q));
  dp_lib_DFFE #(.WIDTH(1))
  ff_s6_s7_negative_zero_s7 (.clock(clock), .in_en(rst_n & valid_q[5]), .in_d(negative_zero_s6_q), .out_q(negative_zero_s7_q));
  dp_lib_DFFE #(.WIDTH(`DP_SPECIAL_W))
  ff_s6_s7_special_s7 (.clock(clock), .in_en(rst_n & valid_q[5]), .in_d(special_s6_q), .out_q(special_s7_q));
  // verilog_format: on

  wire [`DP_FP32_W-1:0] finite_result;
  // [S8 有限结果转换] 对 S7 总和做 abs/LZD/归一化和唯一一次 FP32 RNE。
  // NaN/invalid/Inf 的最终选择在输出 DFF 输入完成，不在这里伪装成普通有限值。
  dp_fp32_round #(
    .SUM_W(SUM_W),
    .ANCHOR_W(ANCHOR_W),
    .GLOBAL_MAG_W(GLOBAL_MAG_W)
  ) u_fp32_output (
    .in_sum(sum_q),
    .in_anchor(common_s7_q),
    .in_negative_zero(negative_zero_s7_q),
    .out_bits(finite_result)
  );

  // [S8 输出选择] 组合数值选择在 DFF 外明确表达，寄存器只保存选定结果。
  wire [`DP_FP32_W-1:0] result_s8_d;
  assign result_s8_d = (special_s7_q[`DP_SP_NAN] | special_s7_q[`DP_SP_INVALID]) ?
    `DP_FP32_QNAN : (special_s7_q[`DP_SP_POS_INF] | special_s7_q[`DP_SP_NEG_INF]) ?
    (`DP_FP32_INF | {special_s7_q[`DP_SP_NEG_INF], {(`DP_FP32_W - 1) {1'b0}}}) : finite_result;

  // [S8 寄存边界] 捕获最终结果及 valid/last；L8/II=1，未新增寄存级。
  // verilog_format: off
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_valid (.clock(clock), .rst_n(rst_n), .in_d(valid_q[6]), .out_q(valid_q[7]));
  dp_lib_DFFRU #(.WIDTH(1))
  ff_s7_s8_last (.clock(clock), .rst_n(rst_n), .in_d(last_q[6]), .out_q(last_q[7]));
  dp_lib_DFFE #(.WIDTH(`DP_FP32_W))
  ff_s7_s8_out_d (.clock(clock), .in_en(rst_n & valid_q[6]), .in_d(result_s8_d), .out_q(out_d));
  // verilog_format: on

  // Elaboration constraints are validation only; no synthesized datapath/reset.
  // synthesis translate_off
  initial begin
    if (K_FP16 != 4 && K_FP16 != 8 && K_FP16 != 16) begin
      $display("FAIL: %s", "K_FP16 must be 4, 8 or 16");
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
