`include "dp_defs.vh"
// S2 输入直接使用紧凑 M32；H 取低 11/8 位，Q 取低两 nibble，E 取四 nibble。
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
  // 与紧凑 S1 字段同拍的格式，控制 S2 计算路由。
  // verilog_format: off
  input wire [`DP_TYPE_W-1:0]                 in_datatype,
  // S1 有效位；气泡时隔离共享算术单元的输入。
  input wire                                  in_enable,
  // A 的紧凑 M32：每 bank 一个 M16，按当前格式取字段。
  input wire [`DP_UNPACK_MANT_W-1:0]          in_a_mantissas,
  // B 的紧凑 M32，与 A 使用相同位片。
  input wire [`DP_UNPACK_MANT_W-1:0]          in_b_mantissas,
  // S2 各元素完整无符号乘积；未用槽为零，符号另传。
  output wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] out_products
  // verilog_format: on
);
  // 生成期共享 bank 索引，每 lane 两套计算资源。
  genvar bank_index;
  // 生成期元素索引，不是运行时计数器。
  genvar element_index;

  `include "dp_functions.vh"
  // [共享结构] 两个 bank 各有 HH/HL/LH/LL 四个无符号乘法叶。
  // H/L 表示操作数的高/低分段，具体宽度来自 DP_MUL_HI/LO；符号不参与乘法。
  // verilog_format: off
  wire [`DP_PRODUCT_W-1:0] bank_products[0:`DP_MUL_BANKS-1][0:3];
  // verilog_format: on
  generate
    for (bank_index = 0; bank_index < `DP_MUL_BANKS; bank_index = bank_index + 1) begin : g_bank
      // HH 叶 A 输入，宽 DP_MUL_HI；格式选择后的幅值位片。
      // verilog_format: off
      wire [`DP_MUL_HI-1:0]            hh_a;
      // HH 叶 B 输入，与 A 配对。
      wire [`DP_MUL_HI-1:0]            hh_b;
      // HL 叶 A 输入，宽 DP_MUL_HI。
      wire [`DP_MUL_HI-1:0]            hl_a;
      // LH 叶 B 输入，宽 DP_MUL_HI。
      wire [`DP_MUL_HI-1:0]            lh_b;
      // HL 叶 B 输入，宽 DP_MUL_LO。
      wire [`DP_MUL_LO-1:0]            hl_b;
      // LH 叶 A 输入，宽 DP_MUL_LO。
      wire [`DP_MUL_LO-1:0]            lh_a;
      // LL 叶 A 输入，宽 DP_MUL_LO。
      wire [`DP_MUL_LO-1:0]            ll_a;
      // LL 叶 B 输入，宽 DP_MUL_LO。
      wire [`DP_MUL_LO-1:0]            ll_b;
      // HH 叶无符号乘积，保留完整自然位宽。
      wire [2*`DP_MUL_HI-1:0]          hh;
      // HL 叶无符号乘积，保留完整自然位宽。
      wire [`DP_MUL_HI+`DP_MUL_LO-1:0] hl;
      // LH 叶无符号乘积，保留完整自然位宽。
      wire [`DP_MUL_HI+`DP_MUL_LO-1:0] lh;
      // LL 叶无符号乘积，保留完整自然位宽。
      wire [2*`DP_MUL_LO-1:0]          ll;
      // bank 第一个逻辑乘积；T/FP16 在此完成四叶加权重构。
      wire [`DP_PRODUCT_W-1:0]         product_first;
      // bank 第二个逻辑乘积；INT8 奇元素在此完成两叶重构。
      wire [`DP_PRODUCT_W-1:0]         product_second;
      // bank 第三个逻辑乘积，仅 E 模式使用。
      wire [`DP_PRODUCT_W-1:0]         product_third;
      // bank 第四个逻辑乘积，仅 E 模式使用。
      wire [`DP_PRODUCT_W-1:0]         product_fourth;
      // HH 乘积零扩展到统一宽度，避免重构移位提前截断。
      wire [`DP_PRODUCT_W-1:0]         hh_extended;
      assign hh_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_HI)) {1'b0}}, hh};
      // verilog_format: on
      // HL 乘积零扩展，保留后续移位所需高位。
      // verilog_format: off
      wire [`DP_PRODUCT_W-1:0] hl_extended;
      assign hl_extended = {{(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, hl};
      // verilog_format: on
      // LH 乘积零扩展，保留后续移位所需高位。
      // verilog_format: off
      wire [`DP_PRODUCT_W-1:0] lh_extended;
      assign lh_extended = {{(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, lh};
      // verilog_format: on
      // LL 乘积零扩展，不改变数值或小数位。
      // verilog_format: off
      wire [`DP_PRODUCT_W-1:0] ll_extended;
      assign ll_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_LO)) {1'b0}}, ll};
      // verilog_format: on
      // 从当前 M16 低 11 位读取 A 的 T/H coefficient。
      // verilog_format: off
      wire [`DP_MANT_W-1:0] h_magnitude_a;
      assign h_magnitude_a = in_a_mantissas[bank_index*`DP_HALF_W+:`DP_MANT_W];
      // verilog_format: on
      // 从当前 M16 低 11 位读取 B 的 T/H coefficient。
      // verilog_format: off
      wire [`DP_MANT_W-1:0] h_magnitude_b;
      assign h_magnitude_b = in_b_mantissas[bank_index*`DP_HALF_W+:`DP_MANT_W];
      // verilog_format: on
      // A 的 Q/INT8 偶元素：Q 取低 nibble，INT8 取低 byte。
      // verilog_format: off
      wire [`DP_QUARTER_W-1:0] q_even_magnitude_a;
      assign q_even_magnitude_a = (in_datatype == `DP_DT_INT8) ? in_a_mantissas[bank_index*`DP_HALF_W+0+:`DP_QUARTER_W] :
                                                                 {{(`DP_QUARTER_W-`DP_MUL_LO){1'b0}}, in_a_mantissas[bank_index*`DP_HALF_W+0+:`DP_MUL_LO]};
      // verilog_format: on
      // B 的 Q/INT8 偶元素，与 A 同位片。
      // verilog_format: off
      wire [`DP_QUARTER_W-1:0] q_even_magnitude_b;
      assign q_even_magnitude_b = (in_datatype == `DP_DT_INT8) ? in_b_mantissas[bank_index*`DP_HALF_W+0+:`DP_QUARTER_W] :
                                                                 {{(`DP_QUARTER_W-`DP_MUL_LO){1'b0}}, in_b_mantissas[bank_index*`DP_HALF_W+0+:`DP_MUL_LO]};
      // verilog_format: on
      // A 的 Q/INT8 奇元素：Q 取第二 nibble，INT8 取高 byte。
      // verilog_format: off
      wire [`DP_QUARTER_W-1:0] q_odd_magnitude_a;
      assign q_odd_magnitude_a = (in_datatype == `DP_DT_INT8) ? in_a_mantissas[bank_index*`DP_HALF_W+`DP_QUARTER_W+:`DP_QUARTER_W] :
                                                                {{(`DP_QUARTER_W-`DP_MUL_LO){1'b0}}, in_a_mantissas[bank_index*`DP_HALF_W+`DP_MUL_LO+:`DP_MUL_LO]};
      // verilog_format: on
      // B 的 Q/INT8 奇元素，与 A 同位片。
      // verilog_format: off
      wire [`DP_QUARTER_W-1:0] q_odd_magnitude_b;
      assign q_odd_magnitude_b = (in_datatype == `DP_DT_INT8) ? in_b_mantissas[bank_index*`DP_HALF_W+`DP_QUARTER_W+:`DP_QUARTER_W] :
                                                                {{(`DP_QUARTER_W-`DP_MUL_LO){1'b0}}, in_b_mantissas[bank_index*`DP_HALF_W+`DP_MUL_LO+:`DP_MUL_LO]};
      // verilog_format: on
      // TF32/FP16 分段乘法使能；TF32 只使用 bank0。
      // verilog_format: off
      wire select_th;
      // BF16 路径使能，只用 HH 叶计算完整 8x8 幅值乘积。
      wire select_bf16;
      // INT8 路径使能，偶元素走 HH、奇元素走 HL/LH 重构。
      wire select_int8;
      // E 格式字段选择，每 atom 四项。
      wire select_e;
      // Q 格式计算路径选择，由格式与有效使能共同控制。
      wire select_q;
      // verilog_format: on

      // [输入选择/隔离] 同一笔 datatype 只激活一种路由；unused 乘法输入置零。
      // TF32 仅 bank0，FP16 分两 bank；BF16、Q、E、INT8 按各自粒度共享这组叶。
      // verilog_format: off
      assign select_th   = in_enable & ((in_datatype == `DP_DT_FP16) | ((in_datatype == `DP_DT_TF32) & (bank_index == 0)));
      assign select_bf16 = in_enable & (in_datatype == `DP_DT_BF16);
      assign select_int8 = in_enable & (in_datatype == `DP_DT_INT8);
      assign select_e    = in_enable & ((in_datatype == `DP_DT_MXFP4) | (in_datatype == `DP_DT_NVFP4) | (in_datatype == `DP_DT_HIF4));
      assign select_q    = in_enable & ~((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16) | (in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) | (elements(in_datatype) == `DP_E_LANES));
      assign hh_a        = select_th   ? {{(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}}, h_magnitude_a[`DP_MANT_W-1:`DP_MUL_LO]} :
                           select_bf16 ? h_magnitude_a[`DP_MUL_HI-1:0] :
                           select_int8 ? q_even_magnitude_a[`DP_MUL_HI-1:0] :
                           select_e    ? {{(`DP_MUL_HI-`DP_MUL_LO){1'b0}}, in_a_mantissas[bank_index*`DP_HALF_W+0*`DP_MUL_LO+:`DP_MUL_LO]} :
                                         0;
      assign hl_a        = select_th   ? hh_a :
                           select_int8 ? q_odd_magnitude_a[`DP_MUL_HI-1:0] :
                           select_e    ? {{(`DP_MUL_HI-`DP_MUL_LO){1'b0}}, in_a_mantissas[bank_index*`DP_HALF_W+1*`DP_MUL_LO+:`DP_MUL_LO]} :
                                         0;
      assign hl_b        = select_th   ? h_magnitude_b[`DP_MUL_LO-1:0] :
                           select_int8 ? q_odd_magnitude_b[`DP_MUL_LO-1:0] :
                           select_e    ? in_b_mantissas[bank_index*`DP_HALF_W+1*`DP_MUL_LO+:`DP_MUL_LO] :
                                         0;
      assign lh_a        = select_th   ? h_magnitude_a[`DP_MUL_LO-1:0] :
                           select_int8 ? q_odd_magnitude_b[`DP_MUL_LO+:`DP_MUL_LO] :
                           select_e    ? in_a_mantissas[bank_index*`DP_HALF_W+2*`DP_MUL_LO+:`DP_MUL_LO] :
                           select_q    ? q_odd_magnitude_a[`DP_MUL_LO-1:0] :
                                         0;
      assign lh_b        = select_th   ? hh_b :
                           select_int8 ? q_odd_magnitude_a[`DP_MUL_HI-1:0] :
                           select_e    ? {{(`DP_MUL_HI-`DP_MUL_LO){1'b0}}, in_b_mantissas[bank_index*`DP_HALF_W+2*`DP_MUL_LO+:`DP_MUL_LO]} :
                           select_q    ? q_odd_magnitude_b[`DP_MUL_HI-1:0] :
                                         0;
      assign ll_a        = select_th ? h_magnitude_a[`DP_MUL_LO-1:0] :
                           select_e  ? in_a_mantissas[bank_index*`DP_HALF_W+3*`DP_MUL_LO+:`DP_MUL_LO] :
                           select_q  ? q_even_magnitude_a[`DP_MUL_LO-1:0] :
                                       0;
      assign ll_b        = select_th ? h_magnitude_b[`DP_MUL_LO-1:0] :
                           select_e  ? in_b_mantissas[bank_index*`DP_HALF_W+3*`DP_MUL_LO+:`DP_MUL_LO] :
                           select_q  ? q_even_magnitude_b[`DP_MUL_LO-1:0] :
                                       0;
      assign hh_b        = select_th   ? {{(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}}, h_magnitude_b[`DP_MANT_W-1:`DP_MUL_LO]} :
                           select_bf16 ? h_magnitude_b[`DP_MUL_HI-1:0] :
                           select_int8 ? q_even_magnitude_b[`DP_MUL_HI-1:0] :
                           select_e    ? {{(`DP_MUL_HI-`DP_MUL_LO){1'b0}}, in_b_mantissas[bank_index*`DP_HALF_W+0*`DP_MUL_LO+:`DP_MUL_LO]} :
                                         0;
      // verilog_format: on

      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_HI)
      ) u_hh_mul (
        .in_a       (hh_a),
        .in_b       (hh_b),
        .out_product(hh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_LO)
      ) u_hl_mul (
        .in_a       (hl_a),
        .in_b       (hl_b),
        .out_product(hl)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_HI)
      ) u_lh_mul (
        .in_a       (lh_a),
        .in_b       (lh_b),
        .out_product(lh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_LO)
      ) u_ll_mul (
        .in_a       (ll_a),
        .in_b       (ll_b),
        .out_product(ll)
      );
      // [乘积重构] T/FP16 使用 HH*2^(2L)+(HL+LH)*2^L+LL，保留完整 22 位乘积。
      // Q/E 的乘法叶是独立元素乘积，不按分段权重相加；INT8 奇元素使用分段重构。
      // verilog_format: off
      assign product_first                = ((in_datatype == `DP_DT_TF32) | (in_datatype == `DP_DT_FP16))                                          ? (hh_extended << (2 * `DP_MUL_LO)) + ((hl_extended + lh_extended) << `DP_MUL_LO) + ll_extended :
                                            ((in_datatype == `DP_DT_BF16) | (in_datatype == `DP_DT_INT8) | (elements(in_datatype) == `DP_E_LANES)) ? hh_extended :
                                                                                                                                                     ll_extended;
      assign product_second               = (in_datatype == `DP_DT_INT8)           ? hl_extended + (lh_extended << `DP_MUL_LO) :
                                            (elements(in_datatype) == `DP_E_LANES) ? hl_extended :
                                            (elements(in_datatype) == `DP_Q_LANES) ? lh_extended :
                                                                                     0;
      assign product_third                = (elements(in_datatype) == `DP_E_LANES) ? lh_extended : 0;
      assign product_fourth               = (elements(in_datatype) == `DP_E_LANES) ? ll_extended : 0;
      assign bank_products[bank_index][0] = product_first;
      assign bank_products[bank_index][1] = product_second;
      assign bank_products[bank_index][2] = product_third;
      assign bank_products[bank_index][3] = product_fourth;
      // verilog_format: on
    end
  endgenerate
  generate
    for (
      element_index = 0; element_index < `DP_E_LANES; element_index = element_index + 1
    ) begin : g_route
      if (element_index < 2) begin : g_h
        // verilog_format: off
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(in_datatype) < `DP_Q_LANES)  ? bank_products[element_index][0] :
                                                                          (elements(in_datatype) == `DP_Q_LANES) ? bank_products[element_index/2][element_index%2] :
                                                                                                                   bank_products[element_index/4][element_index%4];
        // verilog_format: on
      end else if (element_index < `DP_Q_LANES) begin : g_q
        // verilog_format: off
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(in_datatype) < `DP_Q_LANES)  ? 0 :
                                                                          (elements(in_datatype) == `DP_Q_LANES) ? bank_products[element_index/2][element_index%2] :
                                                                                                                   bank_products[element_index/4][element_index%4];
        // verilog_format: on
      end else begin : g_e
        // verilog_format: off
        assign out_products[element_index*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(in_datatype) == `DP_E_LANES) ? bank_products[element_index/4][element_index%4] :
                                                                                                                   0;
        // verilog_format: on
      end
    end
  endgenerate
endmodule
