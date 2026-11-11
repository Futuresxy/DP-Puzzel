`include "dp_defs.vh"
// 输入为两个紧凑 E10，不把 Q/E 指数逐元素展开到 8 位后再取回。
// Two wide/narrow exponent-adder sets per lane, matching the mantissa banks.
// E products share one e2 sum; Q uses both sums, H/T only the wide sum.
// Unsigned integer exponent sums (F0), including HiF4 e2; no mantissa fields.
module dp_exponent_bank (
  // 与紧凑 S1 字段同拍的格式，控制 S2 计算路由。
  // verilog_format: off
  input wire [`DP_TYPE_W-1:0]                     in_datatype,
  // S1 有效位；气泡时隔离共享算术单元的输入。
  input wire                                      in_enable,
  // A 的紧凑 E20：每 bank 一个 E10。
  input wire [`DP_UNPACK_EXP_W-1:0]               in_a_exponents,
  // B 的紧凑 E20：H 使用低 8 位、Q 使用两组 5 位。
  input wire [`DP_UNPACK_EXP_W-1:0]               in_b_exponents,
  // S2 逐元素无符号指数和，供公共 MAX 与局部对齐使用。
  output wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] out_exponents
  // verilog_format: on
);
  // [S2 指数路径] 和尾数 bank 并行工作：T/H 使用宽和，Q 使用宽/窄两路。
  // HiF4 只需公共 e2 和；MX/NV 元素是定点，指数为零。MAX 不依赖乘法结果数值。
  // verilog_format: off
  wire [`DP_PRODUCT_EXP_W-1:0] wide_sum[0:`DP_MUL_BANKS-1];
  // 两个窄指数加法器的无符号输出，Q 奇数元素使用。
  wire [`DP_Q_EXP_W:0]         narrow_sum[0:`DP_MUL_BANKS-1];
  // verilog_format: on
  // 生成期共享 bank 索引，每 lane 两套计算资源。
  genvar bank_index;
  // 生成期元素索引，不是运行时计数器。
  genvar element_index;
  generate
    for (bank_index = 0; bank_index < `DP_MUL_BANKS; bank_index = bank_index + 1) begin : g_bank
      // 宽加法器 A 输入，T/H 指数、Q 偶元素或共享 e2。
      // verilog_format: off
      wire [`DP_EXP_W-1:0]   a_wide_exponent;
      // 宽加法器 B 输入，与 A 按元素配对。
      wire [`DP_EXP_W-1:0]   b_wide_exponent;
      // 窄加法器 A 输入，仅选择 Q 奇元素的 5 位指数。
      wire [`DP_Q_EXP_W-1:0] a_narrow_exponent;
      // 窄加法器 B 输入，仅选择 Q 奇元素的 5 位指数。
      wire [`DP_Q_EXP_W-1:0] b_narrow_exponent;
      // T/H 格式字段选择；H 每 atom 一项，T 仅 atom0。
      wire                   select_h;
      // E 格式字段选择，每 atom 四项。
      wire                   select_e;
      // Q 格式计算路径选择，由格式与有效使能共同控制。
      wire                   select_q;
      assign select_h          = in_enable & ((in_datatype == `DP_DT_FP16) | (in_datatype == `DP_DT_BF16) | ((in_datatype == `DP_DT_TF32) & (bank_index == 0)));
      assign select_e          = in_enable & (bank_index == 0) & ((in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4));
      assign select_q          = in_enable & ~((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) | (in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) | (in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4));
      assign a_wide_exponent   = select_h ? in_a_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+:`DP_EXP_W] :
                                 select_e ? {{(`DP_EXP_W-1){1'b0}}, in_a_exponents[0]} :
                                 select_q ? {{(`DP_EXP_W-`DP_Q_EXP_W){1'b0}}, in_a_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+:`DP_Q_EXP_W]} :
                                            0;
      assign b_wide_exponent   = select_h ? in_b_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+:`DP_EXP_W] :
                                 select_e ? {{(`DP_EXP_W-1){1'b0}}, in_b_exponents[0]} :
                                 select_q ? {{(`DP_EXP_W-`DP_Q_EXP_W){1'b0}}, in_b_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+:`DP_Q_EXP_W]} :
                                            0;
      assign a_narrow_exponent = select_q ? in_a_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+`DP_Q_EXP_W+:`DP_Q_EXP_W] :
                                            0;
      assign b_narrow_exponent = select_q ? in_b_exponents[bank_index*`DP_UNPACK_ATOM_EXP_W+`DP_Q_EXP_W+:`DP_Q_EXP_W] :
                                            0;
      // verilog_format: on

      dp_exponent_add #(
        .W(`DP_EXP_W)
      ) u_wide_add (
        .in_a   (a_wide_exponent),
        .in_b   (b_wide_exponent),
        .out_sum(wide_sum[bank_index])
      );
      dp_exponent_add #(
        .W(`DP_Q_EXP_W)
      ) u_narrow_add (
        .in_a   (a_narrow_exponent),
        .in_b   (b_narrow_exponent),
        .out_sum(narrow_sum[bank_index])
      );
    end
  endgenerate
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_route
      // 当前输出路由为 E，所有元素使用同一 e2 指数和。
      // verilog_format: off
      wire is_e;
      assign is_e = (in_datatype == `DP_DT_MXFP4 | in_datatype == `DP_DT_NVFP4 | in_datatype == `DP_DT_HIF4);
      // verilog_format: on
      // 当前输出路由为 T/H，每 bank 对应一个元素。
      // verilog_format: off
      wire is_h;
      assign is_h = (in_datatype == `DP_DT_TF32 | in_datatype == `DP_DT_FP16 | in_datatype == `DP_DT_BF16);
      // verilog_format: on
      // 当前 Q 元素的宽/窄指数和，显式零扩展到统一输出宽度。
      // verilog_format: off
      wire [`DP_PRODUCT_EXP_W-1:0] q_sum;
      // verilog_format: on
      if (element_index < `DP_Q_LANES & element_index % 2 == 0) begin : g_even
        // verilog_format: off
        assign q_sum = wide_sum[element_index/2];
        // verilog_format: on
      end else if (element_index < `DP_Q_LANES) begin : g_odd
        // verilog_format: off
        assign q_sum = { {(`DP_PRODUCT_EXP_W - `DP_Q_EXP_W - 1) {1'b0}}, narrow_sum[element_index/2] };
        // verilog_format: on
      end else begin : g_unused
        // verilog_format: off
        assign q_sum = 0;
        // verilog_format: on
      end
      if (element_index < `DP_MUL_BANKS) begin : g_h
        // verilog_format: off
        assign out_exponents[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] = is_e ? wide_sum[0] :
                                                                                   is_h ? wide_sum[element_index] :
                                                                                          q_sum;
        // verilog_format: on
      end else begin : g_other
        // verilog_format: off
        assign out_exponents[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] = is_e ? wide_sum[0] :
                                                                                   is_h ? 0 :
                                                                                          q_sum;
        // verilog_format: on
      end
    end
  endgenerate
endmodule
