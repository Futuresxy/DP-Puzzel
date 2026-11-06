`include "dp_defs.vh"
// S5 unsigned scale multiply. A=magnitude, B=scale pair, Y=product.
// Precision | A S | A I | A F | B S | B I | B F | Y S | Y I | Y F
// --------- | --- | --- | --- | --- | --- | --- | --- | --- | ---
// NVFP4     | 0   | 10  | 4   | 0   | 2   | 6   | 0   | 12  | 10
// HiF4 multi| 0   | 8   | 6   | 0   | 2   | 6   | 0   | 10  | 12
// HiF4 E   | 0   | 10  | 4   | 0   | 2   | 6   | 0   | 12  | 10
// Sign travels separately.
module dp_scale_multiply #(
  parameter integer MAG_W   = `DP_SCALE_SOP_W - 1,
  parameter integer COEFF_W = 2 * `DP_SCALE_M
) (
  input wire [MAG_W-1:0] in_magnitude,
  input wire [COEFF_W-1:0] in_coefficient,
  output wire [MAG_W+COEFF_W-1:0] out_product
);

  // [完整 unsigned 乘法] 先在 group 取 abs，本模块不接收补码符号，也不负责舍入。
  // 输出宽度 MAG_W+COEFF_W；低补零、scale 旁路和负号恢复均由上层明确安排。
  // 同宽接口下多精度 HiF4 和 E-only HiF4 的 F 不同，解释时使用各自 group 合同。
  assign out_product = in_magnitude * in_coefficient;
endmodule
