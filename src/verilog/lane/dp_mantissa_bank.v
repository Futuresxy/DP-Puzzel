`include "dp_defs.vh"
// S2 combinational lane multiplier bank: exactly two HH/HL/LH/LL sets.
// Muxes isolate unused multiplier operands. T/H partial products, Q/E independent
// products and the second INT8 split product share these physical instances.
// Unsigned multiplier operands -> logical products (zero-extended in the bus):
// TF32/FP16 S0I1F10 -> S0I2F20. HH uses I1F6 halves, LL I0F4;
// HH/HL/LH/LL partial products are I2F12/I1F10/I1F10/I0F8.
// BF16 S0I1F7 -> S0I2F14. MXFP8 E4M3/E5M2 and MXFP6 E3M2/E2M3
// S0I1F3 -> S0I2F6. MXFP4/NVFP4 S0I3F1 -> S0I6F2.
// HiF4 S0I2F2 -> S0I4F4. INT8 S0I8F0 -> S0I16F0, with the
// split operand treated as two I4F0 digits (upper digit weighted by 2^4).
module dp_mantissa_bank (
  // verilog_format: off  // Keep ports sharing one declaration on the same line.
  input wire [`DP_TYPE_W-1:0] in_datatype,
  input wire in_enable,
  input wire [`DP_E_LANES*`DP_MANT_W-1:0] in_a,in_b,
  output wire [`DP_E_LANES*`DP_PRODUCT_W-1:0] out_products
  // verilog_format: on
);
  genvar bank, i;

  `include "dp_functions.vh"
  wire [`DP_PRODUCT_W-1:0] result[0:`DP_MUL_BANKS-1][0:3];
  generate
    for (bank = 0; bank < `DP_MUL_BANKS; bank = bank + 1) begin : g_bank
      reg [`DP_MUL_HI-1:0] hh_a, hh_b, hl_a, lh_b;
      reg [`DP_MUL_LO-1:0] hl_b, lh_a, ll_a, ll_b;
      wire [2*`DP_MUL_HI-1:0] hh;
      wire [`DP_MUL_HI+`DP_MUL_LO-1:0] hl, lh;
      wire [2*`DP_MUL_LO-1:0] ll;
      reg [`DP_PRODUCT_W-1:0] p0, p1, p2, p3;
      wire [`DP_PRODUCT_W-1:0] hh_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_HI)) {1'b0}}, hh};
      wire [`DP_PRODUCT_W-1:0] hl_extended = {
        {(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, hl
      };
      wire [`DP_PRODUCT_W-1:0] lh_extended = {
        {(`DP_PRODUCT_W - (`DP_MUL_HI + `DP_MUL_LO)) {1'b0}}, lh
      };
      wire [`DP_PRODUCT_W-1:0] ll_extended = {{(`DP_PRODUCT_W - (2 * `DP_MUL_LO)) {1'b0}}, ll};
      wire [`DP_MANT_W-1:0] a_h = in_a[bank*`DP_MANT_W+:`DP_MANT_W],
        b_h = in_b[bank*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] a_q0 = in_a[(bank*2)*`DP_MANT_W+:`DP_MANT_W],
        b_q0 = in_b[(bank*2)*`DP_MANT_W+:`DP_MANT_W];
      wire [`DP_MANT_W-1:0] a_q1 = in_a[(bank*2+1)*`DP_MANT_W+:`DP_MANT_W],
        b_q1 = in_b[(bank*2+1)*`DP_MANT_W+:`DP_MANT_W];
      always @* begin
        hh_a = 0;
        hh_b = 0;
        hl_a = 0;
        hl_b = 0;
        lh_a = 0;
        lh_b = 0;
        ll_a = 0;
        ll_b = 0;
        if (in_enable) begin
          case (in_datatype)
            `DP_DT_TF32, `DP_DT_FP16:
            if (in_datatype == `DP_DT_FP16 || bank == 0) begin
              hh_a = {
                {(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}}, a_h[`DP_MANT_W-1:`DP_MUL_LO]
              };
              hh_b = {
                {(`DP_MUL_HI - (`DP_MANT_W - `DP_MUL_LO)) {1'b0}}, b_h[`DP_MANT_W-1:`DP_MUL_LO]
              };
              hl_a = hh_a;
              hl_b = b_h[`DP_MUL_LO-1:0];
              lh_a = a_h[`DP_MUL_LO-1:0];
              lh_b = hh_b;
              ll_a = a_h[`DP_MUL_LO-1:0];
              ll_b = b_h[`DP_MUL_LO-1:0];
            end
            `DP_DT_BF16: begin
              hh_a = a_h[`DP_MUL_HI-1:0];
              hh_b = b_h[`DP_MUL_HI-1:0];
            end
            `DP_DT_INT8: begin
              hh_a = a_q0[`DP_MUL_HI-1:0];
              hh_b = b_q0[`DP_MUL_HI-1:0];
              hl_a = a_q1[`DP_MUL_HI-1:0];
              hl_b = b_q1[`DP_MUL_LO-1:0];
              lh_a = b_q1[`DP_MUL_LO+:`DP_MUL_LO];
              lh_b = a_q1[`DP_MUL_HI-1:0];
            end
            `DP_DT_MXFP4, `DP_DT_NVFP4, `DP_DT_HIF4: begin
              hh_a = in_a[(bank*4)*`DP_MANT_W+:`DP_MUL_HI];
              hh_b = in_b[(bank*4)*`DP_MANT_W+:`DP_MUL_HI];
              hl_a = in_a[(bank*4+1)*`DP_MANT_W+:`DP_MUL_HI];
              hl_b = in_b[(bank*4+1)*`DP_MANT_W+:`DP_MUL_LO];
              lh_a = in_a[(bank*4+2)*`DP_MANT_W+:`DP_MUL_LO];
              lh_b = in_b[(bank*4+2)*`DP_MANT_W+:`DP_MUL_HI];
              ll_a = in_a[(bank*4+3)*`DP_MANT_W+:`DP_MUL_LO];
              ll_b = in_b[(bank*4+3)*`DP_MANT_W+:`DP_MUL_LO];
            end
            default: begin
              ll_a = a_q0[`DP_MUL_LO-1:0];
              ll_b = b_q0[`DP_MUL_LO-1:0];
              lh_a = a_q1[`DP_MUL_LO-1:0];
              lh_b = b_q1[`DP_MUL_HI-1:0];
            end
          endcase
        end
      end
      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_HI)
      ) hh_mul (
        .in_a(hh_a),
        .in_b(hh_b),
        .out_product(hh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_HI),
        .B_W(`DP_MUL_LO)
      ) hl_mul (
        .in_a(hl_a),
        .in_b(hl_b),
        .out_product(hl)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_HI)
      ) lh_mul (
        .in_a(lh_a),
        .in_b(lh_b),
        .out_product(lh)
      );
      dp_mul_unsigned #(
        .A_W(`DP_MUL_LO),
        .B_W(`DP_MUL_LO)
      ) ll_mul (
        .in_a(ll_a),
        .in_b(ll_b),
        .out_product(ll)
      );
      always @* begin
        p0 = 0;
        p1 = 0;
        p2 = 0;
        p3 = 0;
        case (in_datatype)
          `DP_DT_TF32, `DP_DT_FP16:
          p0 = (hh_extended << (2 * `DP_MUL_LO)) + ((hl_extended + lh_extended) << `DP_MUL_LO) +
            ll_extended;
          `DP_DT_BF16: p0 = hh_extended;
          `DP_DT_INT8: begin
            p0 = hh_extended;
            p1 = hl_extended + (lh_extended << `DP_MUL_LO);
          end
          `DP_DT_MXFP4, `DP_DT_NVFP4, `DP_DT_HIF4: begin
            p0 = hh_extended;
            p1 = hl_extended;
            p2 = lh_extended;
            p3 = ll_extended;
          end
          default: begin
            p0 = ll_extended;
            p1 = lh_extended;
          end
        endcase
      end
      assign result[bank][0] = p0;
      assign result[bank][1] = p1;
      assign result[bank][2] = p2;
      assign result[bank][3] = p3;
    end
  endgenerate
  generate
    for (i = 0; i < `DP_E_LANES; i = i + 1) begin : g_route
      if (i < 2) begin : g_h
        assign out_products[i*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) < `DP_Q_LANES) ? result[i][0] : (elements(
          in_datatype
        ) == `DP_Q_LANES) ? result[i/2][i%2] : result[i/4][i%4];
      end else if (i < `DP_Q_LANES) begin : g_q
        assign out_products[i*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) < `DP_Q_LANES) ? 0 : (elements(
          in_datatype
        ) == `DP_Q_LANES) ? result[i/2][i%2] : result[i/4][i%4];
      end else begin : g_e
        assign out_products[i*`DP_PRODUCT_W+:`DP_PRODUCT_W] = (elements(
          in_datatype
        ) == `DP_E_LANES) ? result[i/4][i%4] : 0;
      end
    end
  endgenerate
endmodule
