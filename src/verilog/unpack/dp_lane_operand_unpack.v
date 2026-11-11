`include "dp_defs.vh"
// 单侧 32 位输入解码并保存到 S1：两个 atom，每个 M16/E10/S4。
// 特殊值分类、subnormal 指数、hidden bit、Q bias、FP4/e1 转换只在元素译码中完成。
// NaN/Inf 用 class 表达，数值占位为 magnitude=0/exponent=1；不得在后级再次分类。
// 输出是紧凑字段，不含 8x23 Number；r1 数据仅有效输入时更新，控制有效位由 lane 持有。
// M 是无符号 coefficient：T/H 保留原 F10/F7；Q 为 F3；MX/NV 为 F1；HiF 为 F2。
module dp_lane_operand_unpack #(
  // Static format capability, not a runtime functional input.
  parameter integer QE_ONLY = 0,
  // 分段时钟使能开关；关闭时完全保留旧寄存器实现。
  parameter integer PRECISION_GATING = 0
) (
  // 上升沿流水时钟。
  // verilog_format: off
  input wire                           clock,
  // 同步低有效复位；与 valid 共同屏蔽 payload 捕获。
  input wire                           rst_n,
  // 当前请求有效，S1 payload 仅在有效且不复位时更新。
  input wire                           in_valid,
  // 当前输入格式；按该格式完成 S1 译码。
  input wire [`DP_TYPE_W-1:0]          in_datatype,
  // 与 S1 寄存值同拍的类型，用于恢复被关闭的常量字段。
  input wire [`DP_TYPE_W-1:0]          in_registered_datatype,
  // 单侧原始 32 位 lane 输入，按 datatype 解释各元素。
  input wire [`DP_LANE_W-1:0]          in_data,
  // HiF4 两个 e1 位，每位作用于四个元素，融入幅值一次。
  input wire [1:0]                     in_e1,
  // HiF4 lane 共享 e2 位，保留为后续指数增量。
  input wire                           in_e2,
  // S1 两个 M16 幅值 atom，直接送尾数 bank，不恢复宽元素记录。
  output wire [`DP_UNPACK_MANT_W-1:0]  out_mantissas,
  // S1 两个 E10 指数 atom，直接送指数 bank。
  output wire [`DP_UNPACK_EXP_W-1:0]   out_exponents,
  // S1 两个 S4 符号 atom，位号与分类槽一致。
  output wire [`DP_UNPACK_SIGN_W-1:0]  out_signs,
  // S1 每槽两位 ZERO/FINITE/INF/NAN 分类，维持元素配对位置。
  output wire [`DP_UNPACK_CLASS_W-1:0] out_classes,
  // S1 每槽一位 sNaN 标志，供 A/B 配对生成 invalid。
  output wire [`DP_UNPACK_SIGN_W-1:0]  out_signaling
  // verilog_format: on
);
  // S1 紧凑寄存器；组合解码直接生成 atom 字段，没有逐元素宽 Number 中间层。
  wire [`DP_HALF_W-1:0] r1_mantissas[0:`DP_LANES-1];
  wire [`DP_UNPACK_ATOM_EXP_W-1:0] r1_exponents[0:`DP_LANES-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] r1_signs[0:`DP_LANES-1];
  wire [`DP_UNPACK_ATOM_CLASS_W-1:0] r1_classes[0:`DP_LANES-1];
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0] r1_signaling[0:`DP_LANES-1];
  // 生成期 atom 与分类槽索引。
  genvar atom_index;
  genvar class_index;
  generate
    for (atom_index = 0; atom_index < `DP_LANES; atom_index = atom_index + 1) begin : g_atom
      // 固定 M16/E10/S4 布局的下一拍值；分类和 sNaN 由原始编码同时产生。
      wire [`DP_HALF_W-1:0] mantissa_d;
      wire [`DP_UNPACK_ATOM_EXP_W-1:0] exponent_d;
      wire [`DP_UNPACK_ATOM_SIGN_W-1:0] signs_d;
      wire [`DP_UNPACK_ATOM_CLASS_W-1:0] classes_d;
      wire [`DP_UNPACK_ATOM_SIGN_W-1:0] signaling_d;
      // E 模式用于保留既有分段寄存器门控策略。
      wire select_e;
      assign select_e = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4);

      dp_unpack_atom #(.ATOM_INDEX(atom_index), .QE_ONLY(QE_ONLY)) u_atom_decode (
        .in_data       (in_data),
        .in_datatype   (in_datatype),
        .in_e1         (in_e1),
        .in_e2         (in_e2),
        .out_mantissas (mantissa_d),
        .out_exponents (exponent_d),
        .out_signs     (signs_d),
        .out_classes   (classes_d),
        .out_signaling (signaling_d)
      );
      // S1：保存紧凑布局，payload 无复位，气泡/复位期间保持。
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_HALF_W))
      ff_s0_s1_mantissas (.clock(clock), .in_en(rst_n & in_valid), .in_d(mantissa_d), .out_q(r1_mantissas[atom_index]));
      if (PRECISION_GATING != 0) begin : g_precision_exponents
        // HiF4 只需要最低 e2 位；MX/NV 指数全为零。按捕获类型使能、按 S1 类型重构。
        wire exponent_low_en;
        wire exponent_upper_en;
        wire r1_is_e;
        wire r1_is_hif4;
        wire r1_exponent_low;
        wire [`DP_UNPACK_ATOM_EXP_W-2:0] r1_exponent_upper;
        assign exponent_low_en   = rst_n & in_valid & (~select_e | (in_datatype == `DP_DT_HIF4));
        assign exponent_upper_en = rst_n & in_valid & ~select_e;
        assign r1_is_e            = (in_registered_datatype == `DP_DT_MXFP4) | (in_registered_datatype == `DP_DT_NVFP4) | (in_registered_datatype == `DP_DT_HIF4);
        assign r1_is_hif4         = in_registered_datatype == `DP_DT_HIF4;
        dp_lib_DFFE #(.WIDTH(1))
        ff_s0_s1_exponent_low (.clock(clock), .in_en(exponent_low_en), .in_d(exponent_d[0]), .out_q(r1_exponent_low));
        dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_EXP_W-1))
        ff_s0_s1_exponent_upper (.clock(clock), .in_en(exponent_upper_en), .in_d(exponent_d[`DP_UNPACK_ATOM_EXP_W-1:1]), .out_q(r1_exponent_upper));
        assign r1_exponents[atom_index] = r1_is_e ? {{(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, (r1_is_hif4 & r1_exponent_low)} : {r1_exponent_upper, r1_exponent_low};
      end else begin : g_full_exponents
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_EXP_W))
      ff_s0_s1_exponents (.clock(clock), .in_en(rst_n & in_valid), .in_d(exponent_d), .out_q(r1_exponents[atom_index]));
      end
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_SIGN_W))
      ff_s0_s1_signs (.clock(clock), .in_en(rst_n & in_valid), .in_d(signs_d), .out_q(r1_signs[atom_index]));
      if (PRECISION_GATING != 0) begin : g_precision_classes
        // E 只有 ZERO/FINITE，分类 bit0 仍需保存；bit1 与 sNaN 在读取时恢复零。
        wire special_fields_en;
        wire r1_is_e;
        wire [`DP_UNPACK_ATOM_SIGN_W-1:0] r1_signaling_raw;
        assign special_fields_en = rst_n & in_valid & ~select_e;
        assign r1_is_e = (in_registered_datatype == `DP_DT_MXFP4) | (in_registered_datatype == `DP_DT_NVFP4) | (in_registered_datatype == `DP_DT_HIF4);
        for (class_index = 0; class_index < `DP_UNPACK_ATOM_SIGN_W; class_index = class_index + 1) begin : g_class
          // 分类低位保留零/有限区别，高位仅在支持特殊值的格式下更新。
          wire r1_class_low;
          wire r1_class_high;
          dp_lib_DFFE #(.WIDTH(1))
          ff_s0_s1_class_low (.clock(clock), .in_en(rst_n & in_valid), .in_d(classes_d[class_index*`DP_NUM_CLASS_W]), .out_q(r1_class_low));
          dp_lib_DFFE #(.WIDTH(1))
          ff_s0_s1_class_high (.clock(clock), .in_en(special_fields_en), .in_d(classes_d[class_index*`DP_NUM_CLASS_W+1]), .out_q(r1_class_high));
          assign r1_classes[atom_index][class_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] = {(~r1_is_e & r1_class_high), r1_class_low};
        end
        dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_SIGN_W))
        ff_s0_s1_signaling (.clock(clock), .in_en(special_fields_en), .in_d(signaling_d), .out_q(r1_signaling_raw));
        assign r1_signaling[atom_index] = r1_is_e ? {`DP_UNPACK_ATOM_SIGN_W{1'b0}} : r1_signaling_raw;
      end else begin : g_full_classes
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_CLASS_W))
      ff_s0_s1_classes (.clock(clock), .in_en(rst_n & in_valid), .in_d(classes_d), .out_q(r1_classes[atom_index]));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_SIGN_W))
      ff_s0_s1_signaling (.clock(clock), .in_en(rst_n & in_valid), .in_d(signaling_d), .out_q(r1_signaling[atom_index]));
      end
      // verilog_format: on

      // S1 输出直接连接紧凑字段，不进行逐元素数值展开。
      // verilog_format: off
      assign out_mantissas[atom_index*`DP_HALF_W+:`DP_HALF_W]                                                       = r1_mantissas[atom_index];
      assign out_exponents[atom_index*`DP_UNPACK_ATOM_EXP_W+:`DP_UNPACK_ATOM_EXP_W]                                 = r1_exponents[atom_index];
      assign out_signs[atom_index*`DP_UNPACK_ATOM_SIGN_W+:`DP_UNPACK_ATOM_SIGN_W]                                   = r1_signs[atom_index];
      assign out_classes[atom_index*`DP_UNPACK_ATOM_CLASS_W+:`DP_UNPACK_ATOM_CLASS_W] = r1_classes[atom_index];
      assign out_signaling[atom_index*`DP_UNPACK_ATOM_SIGN_W+:`DP_UNPACK_ATOM_SIGN_W]                               = r1_signaling[atom_index];
      // verilog_format: on
    end
  endgenerate
endmodule
