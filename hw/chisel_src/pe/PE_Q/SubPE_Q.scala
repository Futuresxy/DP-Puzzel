package dp.pe.q

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** Two exact FP8/FP6 products, without the shared design's word-level MAX/RTZ.
  * Decoded UQ1.3 tails use two 4x4 -> UQ2.6 W8 products. Q high tail stays
  * in nibble2, sign lane1. One-cycle S02 result, II=1, Valid-only.
  * Block E8M0 exponent is attached by PEGroup_Q; no scale-tail multiply exists.
  */
class SubPE_Q(alignment: AlignmentConfig = AlignmentConfig()) extends Module {
  override def desiredName: String = "SubPE_Q" + alignment.suffix
  private val cfg = SubPEConfig.forFamily("Q", alignment)
  val io = IO(new RawSubPEIO(cfg, 2, 8))
  val in = io.in_data.bits
  val products = Wire(new RawProducts(2, 8))
  for (lane <- 0 until 2) {
    val mantLow = lane * 8
    val expLow = lane * 5
    val product = in.a_mant(mantLow + 3, mantLow) * in.b_mant(mantLow + 3, mantLow)
    val exponent_sum = in.a_exp(expLow + 4, expLow) +& in.b_exp(expLow + 4, expLow)
    products.magnitude(lane) := product
    products.negative(lane) := (in.a_sign(lane) ^ in.b_sign(lane)) && product.orR
    products.is_zero(lane) := !product.orR
    products.top_anchor(lane) := Mux(product.orR, exponent_sum.zext - 29.S, (-1024).S(11.W))
  }
  products.special := SpecialValueFlags.none
  val s02_valid_q = RegNext(io.in_data.valid, false.B)
  val s02_products_q = RegEnable(products, io.in_data.valid)
  io.out_data.valid := s02_valid_q
  io.out_data.bits := s02_products_q
}
