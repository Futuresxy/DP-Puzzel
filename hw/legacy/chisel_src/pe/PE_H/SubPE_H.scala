package dp.pe.h

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** One exact BF16/FP16 product, with no local alignment or summation.
  * S01 decode -> S02 product: one cycle, II=1. Valid resets, payload holds.
  * FP16/BF16 are embedded into UQ1.10; 11x11 -> UQ2.20 W22 magnitude.
  */
class SubPE_H(alignment: AlignmentConfig = AlignmentConfig()) extends Module {
  override def desiredName: String = "SubPE_H" + alignment.suffix
  private val cfg = SubPEConfig.forFamily("H", alignment)
  val io = IO(new RawSubPEIO(cfg, 1, 22))
  val in = io.in_data.bits
  val is_bf16 = in.ab_type === DataType.bf16
  val a_mant = Mux(is_bf16, Cat(in.a_mant(7, 0), 0.U(3.W)), in.a_mant(11, 1))
  val b_mant = Mux(is_bf16, Cat(in.b_mant(7, 0), 0.U(3.W)), in.b_mant(11, 1))
  val product = a_mant * b_mant
  val a_exp = Mux(is_bf16, in.a_exp(7, 0), in.a_exp(4, 0).pad(8))
  val b_exp = Mux(is_bf16, in.b_exp(7, 0), in.b_exp(4, 0).pad(8))
  val exponent_sum = a_exp +& b_exp
  val top_anchor = exponent_sum.zext - Mux(is_bf16, 254.S(11.W), 30.S(11.W)) + 1.S
  val result = Wire(new RawProducts(1, 22))
  result.magnitude(0) := product
  result.negative(0) := (in.a_sign(0) ^ in.b_sign(0)) && product.orR
  result.is_zero(0) := !product.orR
  result.top_anchor(0) := Mux(product.orR, top_anchor, (-1024).S(11.W))
  result.special := SpecialValueFlags.none
  val s02_valid_q = RegNext(io.in_data.valid, false.B)
  val s02_products_q = RegEnable(result, io.in_data.valid)
  io.out_data.valid := s02_valid_q
  io.out_data.bits := s02_products_q
}
