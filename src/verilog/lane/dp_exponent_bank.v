`include "dp_defs.vh"
// Two wide/narrow exponent-adder sets per lane, matching the mantissa banks.
// E products share one e2 sum; Q uses both sums, H/T only the wide sum.
// Unsigned integer exponent sums (F0), including HiF4 e2; no mantissa fields.
module dp_exponent_bank (
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [`DP_E_LANES*`DP_EXP_W-1:0] in_a,
  input wire [`DP_E_LANES*`DP_EXP_W-1:0] in_b,
  output wire [`DP_E_LANES*`DP_PRODUCT_EXP_W-1:0] out_exponents
);
  // [S2 指数路径] 和尾数 bank 并行工作：T/H 使用宽和，Q 使用宽/窄两路。
  // HiF4 只需公共 e2 和；MX/NV 元素是定点，指数为零。MAX 不依赖乘法结果数值。
  wire [`DP_PRODUCT_EXP_W-1:0] wide_sum[0:`DP_MUL_BANKS-1];
  wire [`DP_Q_EXP_W:0] narrow_sum[0:`DP_MUL_BANKS-1];
  genvar bank_index;
  genvar element_index;
  generate
    for (bank_index = 0; bank_index < `DP_MUL_BANKS; bank_index = bank_index + 1) begin : g_bank
      wire [`DP_EXP_W-1:0] wide_a;
      wire [`DP_EXP_W-1:0] wide_b;
      wire [`DP_Q_EXP_W-1:0] narrow_a;
      wire [`DP_Q_EXP_W-1:0] narrow_b;
      wire select_h;
      wire select_e;
      wire select_q;
      assign select_h = in_enable & ((in_datatype == `DP_DT_FP16) | (in_datatype == `DP_DT_BF16) |
                                     ((in_datatype == `DP_DT_TF32) & (bank_index == 0)));
      assign select_e = in_enable & (bank_index == 0) &
        ((in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) |
         (in_datatype == `DP_DT_HIF4));
      assign select_q = in_enable & ~((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) |
                                      (in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) |
                                      (in_datatype == `DP_DT_MXFP4) |
                                      (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4));
      assign wide_a = select_h ? in_a[bank_index*`DP_EXP_W+:`DP_EXP_W] :
        select_e ? in_a[0+:`DP_EXP_W] : select_q ? in_a[(bank_index*2)*`DP_EXP_W+:`DP_EXP_W] : 0;
      assign wide_b = select_h ? in_b[bank_index*`DP_EXP_W+:`DP_EXP_W] :
        select_e ? in_b[0+:`DP_EXP_W] : select_q ? in_b[(bank_index*2)*`DP_EXP_W+:`DP_EXP_W] : 0;
      assign narrow_a = select_q ? in_a[(bank_index*2+1)*`DP_EXP_W+:`DP_Q_EXP_W] : 0;
      assign narrow_b = select_q ? in_b[(bank_index*2+1)*`DP_EXP_W+:`DP_Q_EXP_W] : 0;
      dp_exponent_add #(
        .W(`DP_EXP_W)
      ) u_wide_add (
        .in_a(wide_a),
        .in_b(wide_b),
        .out_sum(wide_sum[bank_index])
      );
      dp_exponent_add #(
        .W(`DP_Q_EXP_W)
      ) u_narrow_add (
        .in_a(narrow_a),
        .in_b(narrow_b),
        .out_sum(narrow_sum[bank_index])
      );
    end
  endgenerate
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_route
      wire is_e;
      assign is_e = (in_datatype == `DP_DT_MXFP4 | in_datatype == `DP_DT_NVFP4 |
                     in_datatype == `DP_DT_HIF4);
      wire is_h;
      assign is_h = (in_datatype == `DP_DT_TF32 | in_datatype == `DP_DT_FP16 |
                     in_datatype == `DP_DT_BF16);
      wire [`DP_PRODUCT_EXP_W-1:0] q_sum;
      if (element_index < `DP_Q_LANES & element_index % 2 == 0) begin : g_even
        assign q_sum = wide_sum[element_index/2];
      end else if (element_index < `DP_Q_LANES) begin : g_odd
        assign q_sum = {
          {(`DP_PRODUCT_EXP_W - `DP_Q_EXP_W - 1) {1'b0}}, narrow_sum[element_index/2]
        };
      end else begin : g_unused
        assign q_sum = 0;
      end
      if (element_index < `DP_MUL_BANKS) begin : g_h
        assign out_exponents[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] = is_e ?
          wide_sum[0] : is_h ? wide_sum[element_index] : q_sum;
      end else begin : g_other
        assign out_exponents[element_index*`DP_PRODUCT_EXP_W+:`DP_PRODUCT_EXP_W] = is_e ?
          wide_sum[0] : is_h ? 0 : q_sum;
      end
    end
  endgenerate
endmodule
