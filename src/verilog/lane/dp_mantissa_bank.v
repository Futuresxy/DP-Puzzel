`include "dp_defs.vh"
// S2 combinational lane multiplier bank: exactly two HH/HL/LH/LL sets.
// Muxes isolate unused multiplier operands. T/H partial products, Q/E independent
// products and the second INT8 split product share these physical instances.
// S2 unsigned mantissa operands A/B -> product Y. Sign is separate.
// Precision     | A/B S | A/B I | A/B F | Y S | Y I | Y F
// ------------- | ----- | ----- | ----- | --- | --- | ---
// TF32 / FP16   | 0     | 1     | 10    | 0   | 2   | 20
// BF16          | 0     | 1     | 7     | 0   | 2   | 14
// MXFP8 / MXFP6 | 0     | 1     | 3     | 0   | 2   | 6
// MXFP4 / NVFP4 | 0     | 3     | 1     | 0   | 6   | 2
// HiF4          | 0     | 2     | 2     | 0   | 4   | 4
// INT8          | 0     | 8     | 0     | 0   | 16  | 0
// TF32/FP16 unsigned partial products before weighted recombination.
// Precision / signal | S | I | F
// ------------------ | - | - | --
// HH                 | 0 | 2 | 12
// HL                 | 0 | 1 | 10
// LH                 | 0 | 1 | 10
// LL                 | 0 | 0 | 8
// HH operands use I=1,F=6; LL operands use I=0,F=4.
// INT8 splits an operand into I4F0 digits; the upper digit has weight 2^4.
module dp_mantissa_bank (
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [`DP_E_LANES*`DP_MANT_W-1:0] in_a,
  input wire [`DP_E_LANES*`DP_MANT_W-1:0] in_b,
  output wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] out_products
);
  genvar bank_index;
  genvar element_index;

  `include "dp_functions.vh"
  // [共享结构] 两个 bank 各有 HH/HL/LH/LL 四个无符号乘法叶。
  // H/L 表示操作数的高/低分段，具体宽度来自 DP_MUL_HI/LO；符号不参与乘法。
  wire [`DP_PRODUCT_W-1:0] result[0:`DP_MUL_BANKS-1][0:3];
  generate
    for (bank_index = 0; bank_index < `DP_MUL_BANKS; bank_index = bank_index + 1) begin : g_bank
      wire [`DP_MUL_HI-1:0] hh_a;
      wire [`DP_MUL_HI-1:0] hh_b;
      wire [`DP_MUL_HI-1:0] hl_a;
      wire [`DP_MUL_HI-1:0] lh_b;
      wire [`DP_MUL_LO-1:0] hl_b;
      wire [`DP_MUL_LO-1:0] lh_a;
      wire [`DP_MUL_LO-1:0] ll_a;
      wire [`DP_MUL_LO-1:0] ll_b;
      wire [2*`DP_MUL_HI-1:0] hh;
      wire [`DP_MUL_HI+`DP_MUL_LO-1:0] hl;
      wire [`DP_MUL_HI+`DP_MUL_LO-1:0] lh;
      wire [2*`DP_MUL_LO-1:0] ll;
      wire [`DP_PRODUCT_W-1:0] product_first;
      wire [`DP_PRODUCT_W-1:0] product_second;
      wire [`DP_PRODUCT_W-1:0] product_third;
      wire [`DP_PRODUCT_W-1:0] product_fourth;
      wire [`DP_PRODUCT_W-1:0] hh_extended;
      assign hh_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_HI)) {1'b0}}, hh};
      wire [`DP_PRODUCT_W-1:0] hl_extended;
      assign hl_extended = {{(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, hl};
      wire [`DP_PRODUCT_W-1:0] lh_extended;
      assign lh_extended = {{(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, lh};
      wire [`DP_PRODUCT_W-1:0] ll_extended;
      assign ll_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_LO)) {1'b0}}, ll};
      wire [`DP_MANT_W-1:0] h_magnitude_a;
      assign h_magnitude_a = in_a[bank_index*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] h_magnitude_b;
      assign h_magnitude_b = in_b[bank_index*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] q_even_magnitude_a;
      assign q_even_magnitude_a = in_a[(bank_index*2)*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] q_even_magnitude_b;
      assign q_even_magnitude_b = in_b[(bank_index*2)*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] q_odd_magnitude_a;
      assign q_odd_magnitude_a = in_a[(bank_index*2+1)*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] q_odd_magnitude_b;
      assign q_odd_magnitude_b = in_b[(bank_index*2+1)*`DP_MANT_W+:`DP_MANT_W];
      wire select_th;
      wire select_bf16;
      wire select_int8;
      wire select_e;
      wire select_q;
      // [输入选择/隔离] 同一笔 datatype 只激活一种路由；unused 乘法输入置零。
      // TF32 仅 bank0，FP16 分两 bank；BF16、Q、E、INT8 按各自粒度共享这组叶。
      assign select_th = in_enable &
        ((in_datatype == `DP_DT_FP16) | ((in_datatype == `DP_DT_TF32) & (bank_index == 0)));
      assign select_bf16 = in_enable & (in_datatype == `DP_DT_BF16);
      assign select_int8 = in_enable & (in_datatype == `DP_DT_INT8);
      assign select_e = in_enable & ((in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) |
                                     (in_datatype == `DP_DT_HIF4));
      assign select_q =
        in_enable & ~((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) |
                      (in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) | (elements(
        in_datatype
      ) == `DP_E_LANES));
      assign hh_a = select_th ? {{(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}},
                                 h_magnitude_a[`DP_MANT_W-1:`DP_MUL_LO]} : select_bf16 ?
        h_magnitude_a[`DP_MUL_HI-1:0] : select_int8 ? q_even_magnitude_a[`DP_MUL_HI-1:0] :
        select_e ? in_a[(bank_index*4)*`DP_MANT_W+:`DP_MUL_HI] : 0;
      assign hl_a = select_th ? hh_a : select_int8 ? q_odd_magnitude_a[`DP_MUL_HI-1:0] :
        select_e ? in_a[(bank_index*4+1)*`DP_MANT_W+:`DP_MUL_HI] : 0;
      assign hl_b = select_th ? h_magnitude_b[`DP_MUL_LO-1:0] : select_int8 ? q_odd_magnitude_b[
        `DP_MUL_LO-1:0] : select_e ? in_b[(bank_index*4+1)*`DP_MANT_W+:`DP_MUL_LO] : 0;
      assign lh_a = select_th ? h_magnitude_a[`DP_MUL_LO-1:0] : select_int8 ? q_odd_magnitude_b[
        `DP_MUL_LO+:`DP_MUL_LO] : select_e ? in_a[(bank_index*4+2)*`DP_MANT_W+:`DP_MUL_LO] :
        select_q ? q_odd_magnitude_a[`DP_MUL_LO-1:0] : 0;
      assign lh_b = select_th ? hh_b : select_int8 ? q_odd_magnitude_a[`DP_MUL_HI-1:0] :
        select_e ? in_b[(bank_index*4+2)*`DP_MANT_W+:`DP_MUL_HI] :
        select_q ? q_odd_magnitude_b[`DP_MUL_HI-1:0] : 0;
      assign ll_a = select_th ? h_magnitude_a[`DP_MUL_LO-1:0] :
        select_e ? in_a[(bank_index*4+3)*`DP_MANT_W+:`DP_MUL_LO] :
        select_q ? q_even_magnitude_a[`DP_MUL_LO-1:0] : 0;
      assign ll_b = select_th ? h_magnitude_b[`DP_MUL_LO-1:0] :
        select_e ? in_b[(bank_index*4+3)*`DP_MANT_W+:`DP_MUL_LO] :
        select_q ? q_even_magnitude_b[`DP_MUL_LO-1:0] : 0;
      assign hh_b = select_th ? {{(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}},
                                 h_magnitude_b[`DP_MANT_W-1:`DP_MUL_LO]} : select_bf16 ?
        h_magnitude_b[`DP_MUL_HI-1:0] : select_int8 ? q_even_magnitude_b[`DP_MUL_HI-1:0] :
        select_e ? in_b[(bank_index*4)*`DP_MANT_W+:`DP_MUL_HI] : 0;
      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_HI)
      ) u_hh_mul (
        .in_a(hh_a),
        .in_b(hh_b),
        .out_product(hh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_LO)
      ) u_hl_mul (
        .in_a(hl_a),
        .in_b(hl_b),
        .out_product(hl)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_HI)
      ) u_lh_mul (
        .in_a(lh_a),
        .in_b(lh_b),
        .out_product(lh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_LO)
      ) u_ll_mul (
        .in_a(ll_a),
        .in_b(ll_b),
        .out_product(ll)
      );
      // [乘积重构] T/FP16 使用 HH*2^(2L)+(HL+LH)*2^L+LL，保留完整 22 位产品。
      // Q/E 的乘法叶是独立元素产品，不按分段权重相加；INT8 奇元素使用分段重构。
      assign product_first = ((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16)) ?
        (hh_extended << (2 * `DP_MUL_LO)) + ((hl_extended + lh_extended) << `DP_MUL_LO) +
        ll_extended : ((in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) | (elements(
        in_datatype
      ) == `DP_E_LANES)) ? hh_extended : ll_extended;
      assign product_second = (in_datatype == `DP_DT_INT8) ?
        hl_extended + (lh_extended << `DP_MUL_LO) : (elements(
        in_datatype
      ) == `DP_E_LANES) ? hl_extended : (elements(
        in_datatype
      ) == `DP_Q_LANES) ? lh_extended : 0;
      assign product_third = (elements(in_datatype) == `DP_E_LANES) ? lh_extended : 0;
      assign product_fourth = (elements(in_datatype) == `DP_E_LANES) ? ll_extended : 0;
      assign result[bank_index][0] = product_first;
      assign result[bank_index][1] = product_second;
      assign result[bank_index][2] = product_third;
      assign result[bank_index][3] = product_fourth;
    end
  endgenerate
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_route
      if (element_index < 2) begin : g_h
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) < `DP_Q_LANES) ? result[element_index][0] : (elements(
          in_datatype
        ) == `DP_Q_LANES) ? result[element_index/2][element_index%2] :
          result[element_index/4][element_index%4];
      end else if (element_index < `DP_Q_LANES) begin : g_q
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) < `DP_Q_LANES) ? 0 : (elements(
          in_datatype
        ) == `DP_Q_LANES) ? result[element_index/2][element_index%2] :
          result[element_index/4][element_index%4];
      end else begin : g_e
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) == `DP_E_LANES) ? result[element_index/4][element_index%4] : 0;
      end
    end
  endgenerate
endmodule
