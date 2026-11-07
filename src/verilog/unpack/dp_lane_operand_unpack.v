`include "dp_defs.vh"
// 单侧 32 位输入解码并保存到 S1：两个 atom，每个 M16/E10/S4。
// 特殊值分类、subnormal 指数、hidden bit、Q bias、FP4/e1 转换只在元素译码中完成。
// NaN/Inf 用 class 表达，数值占位为 magnitude=0/exponent=1；不得在后级再次分类。
// 输出是紧凑字段，不含 8x23 Number；r1 数据仅有效输入时更新，控制有效位由 lane 持有。
// M 是无符号 coefficient：T/H 保留原 F10/F7；Q 为 F3；MX/NV 为 F1；HiF 为 F2。
module dp_lane_operand_unpack #(
  // Static format capability, not a runtime functional input.
  parameter integer QE_ONLY = 0
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
  // 逐元素组合译码仅存在于本模块内部，分类与数值由同一次译码生成。
  // verilog_format: off
  wire [`DP_MANT_W-1:0]              decoded_magnitude[0:`DP_E_LANES-1];
  // 逐元素有效指数临时连线；Q 已完成 bias 重编码。
  wire [`DP_EXP_W-1:0]               decoded_exponent[0:`DP_E_LANES-1];
  // 逐元素符号，包括零的符号。
  wire                               decoded_negative[0:`DP_E_LANES-1];
  // 逐元素有限/零/Inf/NaN 分类，与幅值同时译码。
  wire [`DP_NUM_CLASS_W-1:0]         decoded_class[0:`DP_E_LANES-1];
  // 逐元素 sNaN 分类，不从安全数值占位反推。
  wire                               decoded_signaling[0:`DP_E_LANES-1];
  // 每个 atom 的 S1 紧凑寄存值；后级仅选择字段，不恢复通用 Number 总线。
  wire [`DP_HALF_W-1:0]              r1_mantissas[0:`DP_LANES-1];
  // S1 每 atom 复用的 E10 寄存值。
  wire [`DP_UNPACK_ATOM_EXP_W-1:0]   r1_exponents[0:`DP_LANES-1];
  // S1 每 atom 的四个符号槽。
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0]  r1_signs[0:`DP_LANES-1];
  // S1 每 atom 的四个两位分类槽。
  wire [`DP_UNPACK_ATOM_CLASS_W-1:0] r1_classes[0:`DP_LANES-1];
  // S1 每 atom 的四个 sNaN 槽。
  wire [`DP_UNPACK_ATOM_SIGN_W-1:0]  r1_signaling[0:`DP_LANES-1];
  // verilog_format: on
  // 生成期元素索引，不是运行时计数器。
  genvar element_index;
  // 生成期 atom 索引；每 lane 两个 16 位原子块。
  genvar atom_index;
  // 生成期 atom 内槽索引，E 模式使用全部四槽。
  genvar slot_index;
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_decode
      dp_operand_unpack #(
        .INDEX(element_index),
        .QE_ONLY(QE_ONLY)
      ) u_decoder (
        .in_data      (in_data),
        .in_datatype  (in_datatype),
        .in_e1        (in_e1),
        .in_e2        (in_e2),
        .out_magnitude(decoded_magnitude[element_index]),
        .out_exponent (decoded_exponent[element_index]),
        .out_negative (decoded_negative[element_index]),
        .out_class    (decoded_class[element_index]),
        .out_signaling(decoded_signaling[element_index])
      );
    end
    for (atom_index = 0; atom_index < `DP_LANES; atom_index = atom_index + 1) begin : g_atom
      // T/H 每 atom 一项，Q/INT 两项，E 四项；TF32 只启用 atom0。
      // verilog_format: off
      wire select_h;
      // E 格式字段选择，每 atom 四项。
      wire select_e;
      // TF32 仅 atom0 有效；其余格式使用两个 atom。
      wire atom_enabled;
      assign select_h     = (QE_ONLY == 0) & ((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) | (in_datatype == `DP_DT_BF16));
      assign select_e     = (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4);
      assign atom_enabled = (QE_ONLY != 0) | (in_datatype != `DP_DT_TF32) | (atom_index == 0);
      // verilog_format: on

      // M16 选择：H 单幅值；Q 两个低 nibble；INT 两字节；E 四 nibble。
      // verilog_format: off
      wire [`DP_HALF_W-1:0] h_mantissa;
      // Q 两个 nibble 或 INT8 两个 byte 拼入 M16。
      wire [`DP_HALF_W-1:0] q_mantissa;
      // E 的四个四位 coefficient 拼入 M16。
      wire [`DP_HALF_W-1:0] e_mantissa;
      // 本 atom 等待 S1 捕获的紧凑幅值。
      wire [`DP_HALF_W-1:0] mantissa_d;
      assign h_mantissa = {{(`DP_HALF_W-`DP_MANT_W){1'b0}}, decoded_magnitude[atom_index]};
      assign q_mantissa = ((QE_ONLY == 0) & (in_datatype == `DP_DT_INT8)) ? {decoded_magnitude[`DP_UNPACK_ATOM_Q_LANES*atom_index+1][0+:`DP_QUARTER_W], decoded_magnitude[`DP_UNPACK_ATOM_Q_LANES*atom_index][0+:`DP_QUARTER_W]} :
                                                         {{(`DP_HALF_W-`DP_UNPACK_ATOM_Q_LANES*`DP_MUL_LO){1'b0}}, decoded_magnitude[`DP_UNPACK_ATOM_Q_LANES*atom_index+1][0+:`DP_MUL_LO], decoded_magnitude[`DP_UNPACK_ATOM_Q_LANES*atom_index][0+:`DP_MUL_LO]};
      assign mantissa_d = ~atom_enabled ? 0 :
                          select_h      ? h_mantissa :
                          select_e      ? e_mantissa :
                                          q_mantissa;
      // verilog_format: on

      // E10：H 为低 8 位；Q 为两个 5 位指数；HiF4 只存 e2；MX/NV/INT 为零。
      // verilog_format: off
      wire [`DP_UNPACK_ATOM_EXP_W-1:0] exponent_d;
      assign exponent_d = ~atom_enabled                ? 0 :
                          select_h                     ? {{(`DP_UNPACK_ATOM_EXP_W-`DP_EXP_W){1'b0}}, decoded_exponent[atom_index]} :
                          select_e                     ? {{(`DP_UNPACK_ATOM_EXP_W-1){1'b0}}, decoded_exponent[atom_index*`DP_UNPACK_ATOM_SIGN_W][0]} :
                          ((QE_ONLY == 0) & (in_datatype == `DP_DT_INT8)) ? 0 :
                                                         {decoded_exponent[`DP_UNPACK_ATOM_Q_LANES*atom_index+1][0+:`DP_Q_EXP_W], decoded_exponent[`DP_UNPACK_ATOM_Q_LANES*atom_index][0+:`DP_Q_EXP_W]};
      // verilog_format: on

      // 符号和分类与 M/E 使用同一槽映射；未用槽清零，保留负零与 sNaN 信息。
      // verilog_format: off
      wire [`DP_UNPACK_ATOM_SIGN_W-1:0]  signs_d;
      // 本 atom 等待 S1 捕获的分类槽。
      wire [`DP_UNPACK_ATOM_CLASS_W-1:0] classes_d;
      // 本 atom 等待 S1 捕获的 sNaN 槽。
      wire [`DP_UNPACK_ATOM_SIGN_W-1:0]  signaling_d;
      // verilog_format: on
      for (
        slot_index = 0; slot_index < `DP_UNPACK_ATOM_SIGN_W; slot_index = slot_index + 1
      ) begin : g_slot
        // 常量索引保证未使用分支也不会越界；是否参与由 select 和槽号共同限定。
        localparam integer Q_INDEX = `DP_UNPACK_ATOM_Q_LANES * atom_index +
          (slot_index % `DP_UNPACK_ATOM_Q_LANES);
        // E 每 atom 四项，按连续元素编号。
        localparam integer E_INDEX = atom_index * `DP_UNPACK_ATOM_SIGN_W + slot_index;
        // verilog_format: off
        assign e_mantissa[slot_index*`DP_MUL_LO+:`DP_MUL_LO]          = decoded_magnitude[E_INDEX][0+:`DP_MUL_LO];
        assign signs_d[slot_index]                                    = ~atom_enabled    ? 0 :
                                                                        select_h         ? ((slot_index == 0) ? decoded_negative[atom_index] : 0) :
                                                                        select_e         ? decoded_negative[E_INDEX] :
                                                                        (slot_index < `DP_UNPACK_ATOM_Q_LANES) ? decoded_negative[Q_INDEX] :
                                                                                           0;
        assign classes_d[slot_index*`DP_NUM_CLASS_W+:`DP_NUM_CLASS_W] = ~atom_enabled    ? 0 :
                                                                        select_h         ? ((slot_index == 0) ? decoded_class[atom_index] : 0) :
                                                                        select_e         ? decoded_class[E_INDEX] :
                                                                        (slot_index < `DP_UNPACK_ATOM_Q_LANES) ? decoded_class[Q_INDEX] :
                                                                                           0;
        assign signaling_d[slot_index]                                = ~atom_enabled    ? 0 :
                                                                        select_h         ? ((slot_index == 0) ? decoded_signaling[atom_index] : 0) :
                                                                        select_e         ? decoded_signaling[E_INDEX] :
                                                                        (slot_index < `DP_UNPACK_ATOM_Q_LANES) ? decoded_signaling[Q_INDEX] :
                                                                                           0;
        // verilog_format: on
      end
      // S1：保存紧凑布局，payload 无复位，气泡/复位期间保持。
      // verilog_format: off
      dp_lib_DFFE #(.WIDTH(`DP_HALF_W))
      ff_s0_s1_mantissas (.clock(clock), .in_en(rst_n & in_valid), .in_d(mantissa_d), .out_q(r1_mantissas[atom_index]));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_EXP_W))
      ff_s0_s1_exponents (.clock(clock), .in_en(rst_n & in_valid), .in_d(exponent_d), .out_q(r1_exponents[atom_index]));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_SIGN_W))
      ff_s0_s1_signs (.clock(clock), .in_en(rst_n & in_valid), .in_d(signs_d), .out_q(r1_signs[atom_index]));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_CLASS_W))
      ff_s0_s1_classes (.clock(clock), .in_en(rst_n & in_valid), .in_d(classes_d), .out_q(r1_classes[atom_index]));
      dp_lib_DFFE #(.WIDTH(`DP_UNPACK_ATOM_SIGN_W))
      ff_s0_s1_signaling (.clock(clock), .in_en(rst_n & in_valid), .in_d(signaling_d), .out_q(r1_signaling[atom_index]));
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
