package dp.pe.qe

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** Low-precision mixed SubPE: FP8/FP6 plus the four-lane FP4 family. */
class SubPE_QE(alignment: AlignmentConfig = AlignmentConfig()) extends SubPEBase(SubPEConfig.forFamily("QE", alignment)) {
  override def desiredName: String = "SubPE_QE" + alignment.suffix
  cfg.requireInputWidths(exp = 10, mant = 16, sign = 4, anchor = 6)
  // ---------------------------------------------------------------------------
  // Fixed-point layout and structural constraints
  // ---------------------------------------------------------------------------
  private val laneProductWidth = cfg.fp8ProductSignedWidth          // 9
  private val fp4PairSumWidth = laneProductWidth + 1                // 10
  private val fp4FinalSumWidth = fp4PairSumWidth + 1                // 11
  private val fp8FinalSumWidth = cfg.fp8RetainWidth + 1
  private val sharedOperandWidth = cfg.outWidth - 1
  private val compactOpAWidth = fp4PairSumWidth                     // 10
  private val fp8GuardBits = cfg.fp8RetainWidth - laneProductWidth
  private val fp4OutputLsbZeros = cfg.outWidth - fp4FinalSumWidth
  private val fp8OutputLsbZeros = cfg.outWidth - fp8FinalSumWidth

  require(fp8GuardBits >= 0, "fp8RetainWidth must hold one signed FP8/FP6 product")
  require(
    fp4OutputLsbZeros >= 0,
    s"SubPELow outWidth=${cfg.outWidth} must hold the $fp4FinalSumWidth-bit FP4 sum"
  )
  require(
    fp8OutputLsbZeros >= 0,
    s"SubPELow outWidth=${cfg.outWidth} must hold the $fp8FinalSumWidth-bit FP8/FP6 sum"
  )

  // ---------------------------------------------------------------------------
  // Elaboration helpers
  // ---------------------------------------------------------------------------
  private def signedProduct(magnitude: UInt, negative: Bool): SInt = {
    val positive = magnitude.zext
    Mux(negative, -positive, positive)
  }

  /** Align the unsigned product directly; apply its sign after logical RTZ. */
  private def alignMagnitude(magnitude: UInt, negative: Bool, lsbZeros: Int, shift: UInt, outWidth: Int): SInt = {
    require(lsbZeros >= 0)
    require(magnitude.getWidth + lsbZeros + 1 == outWidth)
    val extended =
      if (lsbZeros > 0) Cat(magnitude, 0.U(lsbZeros.W))
      else magnitude
    signedProduct(extended >> shift, negative)
  }

  /** Put useful bits at the high side of the shared CPA and keep low guard zeros. */
  private def placeAtSharedAdder(value: SInt, lsbZeros: Int): SInt = {
    require(
      value.getWidth + lsbZeros == sharedOperandWidth,
      s"${value.getWidth}-bit operand plus $lsbZeros zeros must fill $sharedOperandWidth bits"
    )
    if (lsbZeros > 0) Cat(value.asUInt, 0.U(lsbZeros.W)).asSInt else value
  }

  // ---------------------------------------------------------------------------
  // Pipeline control
  // ---------------------------------------------------------------------------
  // PETile S02-S04; accepted transactions and valid bubbles advance every clock.
  val s02_valid_q = RegNext(io.in_data.valid, false.B)
  val s03_valid_q = RegNext(s02_valid_q, false.B)
  val s04_valid_q = RegNext(s03_valid_q, false.B)
  val s01_fire = io.in_data.valid
  val s02_fire = s02_valid_q
  val s03_fire = s03_valid_q

  // ---------------------------------------------------------------------------
  // S01 -> S02: exponent comparison and four independent 4x4 products
  // ---------------------------------------------------------------------------
  val in_data = io.in_data.bits
  val raw_exp_sum_lo = in_data.a_exp(4, 0) +& in_data.b_exp(4, 0)
  val exp_sum_lo = SubPEProductAnchor(raw_exp_sum_lo, in_data.a_mant(3, 0), in_data.b_mant(3, 0))
  val exp_sum_hi = SubPEProductAnchor(
    in_data.a_exp(9, 5) +& in_data.b_exp(9, 5), in_data.a_mant(11, 8), in_data.b_mant(11, 8))
  val s01_hi_is_max = exp_sum_hi > exp_sum_lo
  val s01_fp8_anchor = Mux(s01_hi_is_max, exp_sum_hi, exp_sum_lo)
  val s01_fp8_delta = Mux(s01_hi_is_max, exp_sum_hi - exp_sum_lo, exp_sum_lo - exp_sum_hi)
  val s01_is_fp8 = in_data.ab_type === DataType.e5_m2 || in_data.ab_type === DataType.e4_m3 ||
    in_data.ab_type === DataType.e3_m2 || in_data.ab_type === DataType.e2_m3

  val s01_products = Wire(Vec(4, UInt(8.W)))
  s01_products(0) := in_data.a_mant(3, 0) * in_data.b_mant(3, 0)
  s01_products(1) := in_data.a_mant(7, 4) * in_data.b_mant(7, 4)
  s01_products(2) := in_data.a_mant(11, 8) * in_data.b_mant(11, 8)
  s01_products(3) := in_data.a_mant(15, 12) * in_data.b_mant(15, 12)

  val s02_is_fp8_q = RegEnable(s01_is_fp8, s01_fire)
  val s02_anchor_q = RegEnable(Mux(s01_is_fp8, s01_fp8_anchor, raw_exp_sum_lo), s01_fire)
  val s02_hi_is_max_q = RegEnable(s01_hi_is_max, s01_fire)
  val s02_fp8_delta_q = RegEnable(s01_fp8_delta, s01_fire)
  val s02_products_q = RegEnable(s01_products, s01_fire)
  val s02_negative_q = RegEnable(
    VecInit((0 until 4).map(lane => in_data.a_sign(lane) ^ in_data.b_sign(lane))),
    s01_fire
  )

  // ---------------------------------------------------------------------------
  // S02 -> S03: FP8 lane alignment or FP4 first-level pair sums
  // ---------------------------------------------------------------------------
  val s02_signed_products = Wire(Vec(4, SInt(laneProductWidth.W)))
  for (lane <- 0 until 4) {
    // These signed products feed only the FP4 pair sums. The FP8 high product
    // lives in physical slot 2, but takes its sign from slot 1 below.
    s02_signed_products(lane) := signedProduct(s02_products_q(lane), s02_negative_q(lane))
  }

  val s02_fp8_max_magnitude = Mux(s02_hi_is_max_q, s02_products_q(2), s02_products_q(0))
  val s02_fp8_min_magnitude = Mux(s02_hi_is_max_q, s02_products_q(0), s02_products_q(2))
  val s02_fp8_max_negative = Mux(s02_hi_is_max_q, s02_negative_q(1), s02_negative_q(0))
  val s02_fp8_min_negative = Mux(s02_hi_is_max_q, s02_negative_q(0), s02_negative_q(1))
  val s02_fp8_max_product = signedProduct(s02_fp8_max_magnitude, s02_fp8_max_negative)
  val s02_fp8_min_aligned =
    alignMagnitude(s02_fp8_min_magnitude, s02_fp8_min_negative, fp8GuardBits, s02_fp8_delta_q, cfg.fp8RetainWidth)

  val s02_fp4_pair01 = s02_signed_products(0) +& s02_signed_products(1)
  val s02_fp4_pair23 = s02_signed_products(2) +& s02_signed_products(3)

  // The unshifted FP8 max lane and the FP4 pair01 share one compact S03
  // register.  Appending one LSB zero turns the signed W9 FP8 product into its
  // exact S1-I2-F7 W10 encoding; the FP4 pair sum has its own dtype-specific
  // S1-I7-F2/S1-I5-F4 binary point.  They share a physical W10 register and
  // common static placement, not one numerical binary point.  The remaining
  // W-11 structural zeros are restored only at the shared CPA input.
  val s02_fp8_compact_op_a = Cat(s02_fp8_max_product.asUInt, 0.U(1.W)).asSInt
  require(s02_fp8_compact_op_a.getWidth == compactOpAWidth)
  require(s02_fp4_pair01.getWidth == compactOpAWidth)

  val s02_fp8_op_b = placeAtSharedAdder(s02_fp8_min_aligned, fp8OutputLsbZeros)
  val s02_fp4_op_b = placeAtSharedAdder(s02_fp4_pair23, fp4OutputLsbZeros)

  val s03_compact_op_a_q = RegEnable(Mux(s02_is_fp8_q, s02_fp8_compact_op_a, s02_fp4_pair01), s02_fire)
  val s03_op_b_q = RegEnable(Mux(s02_is_fp8_q, s02_fp8_op_b, s02_fp4_op_b), s02_fire)

  // ---------------------------------------------------------------------------
  // S03 -> S04: shared final carry-propagate adder
  // ---------------------------------------------------------------------------
  val s03_op_a = placeAtSharedAdder(s03_compact_op_a_q, fp4OutputLsbZeros)
  // FP8/FP6 and FP4 are already at the same physical output width. +& preserves
  // the final carry and produces the complete cfg.outWidth-bit signed result.
  val s03_shared_sum = s03_op_a +& s03_op_b_q
  val s04_result_q = RegEnable(s03_shared_sum, s03_fire)

  // ---------------------------------------------------------------------------
  // Interfaces
  // ---------------------------------------------------------------------------

  io.out_anchor.valid := s02_valid_q
  io.out_anchor.bits.subpe_anchor := s02_anchor_q

  io.out_data.valid := s04_valid_q
  io.out_data.bits.result := s04_result_q
}


/* Output fixed-point contract: W = S + I + F; I excludes sign.
 * Format                 W(default) S I F(default)  F for configured W
 * E5M2/E4M3/E3M2/E2M3     29         1 3 25          W-4
 * E2M1/NVFP4             29         1 8 20          W-9
 * HiF4                   29         1 6 22          W-7
 * FP8 retained single lane: W28 = S1/I2/F25. MAX stores its compact product.
 * Result latency 3 clocks; early anchor latency 1 clock; no backpressure.
 */
