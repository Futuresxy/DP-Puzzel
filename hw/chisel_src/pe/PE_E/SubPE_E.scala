package dp.pe.e

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** Four-lane MXFP4/NVFP4/HiF4 dot-product SubPE. */
class SubPE_E(alignment: AlignmentConfig = AlignmentConfig()) extends SubPEBase(SubPEConfig.forFamily("E", alignment)) {
  override def desiredName: String = "SubPE_E" + alignment.suffix
  // ---------------------------------------------------------------------------
  // Fixed-point layout and structural constraints
  // ---------------------------------------------------------------------------
  private val laneCount = 4
  private val laneMantWidth = 4
  private val laneProductWidth = SubPEFixedPoint.fp4_lane_product.width // S1 + I6 + F2 = 9
  private val pairSumWidth = laneProductWidth + 1                     // 10
  private val dotSumWidth = pairSumWidth + 1                          // 11
  private val outputLsbZeros = cfg.outWidth - dotSumWidth

  require(
    cfg.mantWidth >= laneCount * laneMantWidth,
    s"FP4 SubPE requires at least ${laneCount * laneMantWidth} mantissa bits"
  )
  require(
    cfg.signGroupWidth >= laneCount,
    s"FP4 SubPE requires at least $laneCount sign bits"
  )
  require(
    outputLsbZeros >= 0,
    s"FP4 SubPE outWidth=${cfg.outWidth} must hold the $dotSumWidth-bit four-lane sum"
  )

  // ---------------------------------------------------------------------------
  // Elaboration helpers
  // ---------------------------------------------------------------------------
  private def signedProduct(magnitude: UInt, negative: Bool): SInt = {
    val positive = magnitude.zext
    Mux(negative, -positive, positive)
  }

  /**
    * Place the exact 11-bit local sum at the configured output binary point.
    * This is constant wiring: useful bits stay on the high side and all added
    * fractional guard positions are zeros.  No rounding or truncation occurs.
    */
  private def placeAtOutput(value: SInt): SInt = {
    require(value.getWidth == dotSumWidth)
    if (outputLsbZeros > 0) Cat(value.asUInt, 0.U(outputLsbZeros.W)).asSInt else value
  }

  // ---------------------------------------------------------------------------
  // Pipeline control
  // ---------------------------------------------------------------------------
  // After the S01 raw-input register and decode, these are PETile S02-S04.
  val s02_valid_q = RegNext(io.in_data.valid, false.B)
  val s03_valid_q = RegNext(s02_valid_q, false.B)
  val s04_valid_q = RegNext(s03_valid_q, false.B)
  val s01_fire = io.in_data.valid
  val s02_fire = s02_valid_q
  val s03_fire = s03_valid_q

  // ---------------------------------------------------------------------------
  // S01 -> S02: four independent 4x4 products and sign application
  // ---------------------------------------------------------------------------
  val s01_lane_products = Wire(Vec(laneCount, SInt(laneProductWidth.W)))
  for (lane <- 0 until laneCount) {
    val hi = (lane + 1) * laneMantWidth - 1
    val lo = lane * laneMantWidth
    val magnitude = io.in_data.bits.a_mant(hi, lo) * io.in_data.bits.b_mant(hi, lo)
    val negative = io.in_data.bits.a_sign(lane) ^ io.in_data.bits.b_sign(lane)
    s01_lane_products(lane) := signedProduct(magnitude, negative)
  }
  val s02_lane_products_q = RegEnable(s01_lane_products, s01_fire)

  // ---------------------------------------------------------------------------
  // S02 -> S03: balanced first adder-tree level (9b + 9b -> 10b)
  // ---------------------------------------------------------------------------
  val s02_pair01 = s02_lane_products_q(0) +& s02_lane_products_q(1)
  val s02_pair23 = s02_lane_products_q(2) +& s02_lane_products_q(3)
  val s03_pair01_q = RegEnable(s02_pair01, s02_fire)
  val s03_pair23_q = RegEnable(s02_pair23, s02_fire)

  // ---------------------------------------------------------------------------
  // S03 -> S04: final adder-tree level (10b + 10b -> exact 11b sum)
  // ---------------------------------------------------------------------------
  val s03_dot_sum = s03_pair01_q +& s03_pair23_q
  val s04_dot_sum_q = RegEnable(s03_dot_sum, s03_fire)

  // ---------------------------------------------------------------------------
  // Interfaces
  // ---------------------------------------------------------------------------

  // FP4-only PEGroup owns the early anchor/type path. The common SubPEBase port
  // remains present for interface compatibility and is intentionally tied off.
  io.out_anchor.valid := false.B
  io.out_anchor.bits.subpe_anchor := 0.U(cfg.subpeAnchorWidth.W)

  io.out_data.valid := s04_valid_q
  io.out_data.bits.result := placeAtOutput(s04_dot_sum_q)
}


/* Output fixed-point contract: W = S + I + F; I excludes sign.
 * Format       W(dedicated) S I F(default)  F for configured W
 * E2M1/NVFP4   11         1 8 2           W-9
 * HiF4         11         1 6 4           W-7
 * Dedicated PEGroup config uses W11; wider explicit configs append exact zeros.
 * Exact products and exact three-clock local sum; no rounding, no backpressure.
 * The dedicated PEGroup owns the anchor; this leaf's anchor port is tied off.
 */
