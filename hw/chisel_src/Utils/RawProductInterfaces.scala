package dp.utils

import chisel3._
import chisel3.util._
import dp.config.SpecialValueFlags

/** Atomic unaligned products. top_anchor is the exponent of magnitude's MSB.
  * No lane sum or alignment occurs in the H/Q SubPE/PG product clusters.
  */
class RawProducts(laneCount: Int, magnitudeWidth: Int) extends Bundle {
  val magnitude = Vec(laneCount, UInt(magnitudeWidth.W))
  val negative = Vec(laneCount, Bool())
  val top_anchor = Vec(laneCount, SInt(11.W))
  val is_zero = Vec(laneCount, Bool())
  val special = new SpecialValueFlags
}
class RawSubPEIO(cfg: SubPEConfig, laneCount: Int, magnitudeWidth: Int) extends Bundle {
  val in_data = Flipped(Valid(new SubPEInput(cfg)))
  val out_data = Valid(new RawProducts(laneCount, magnitudeWidth))
}
class RawGroupIO(laneCount: Int, magnitudeWidth: Int) extends Bundle {
  val in_data = Flipped(Valid(new PEGroupInput(4, 1, 4, 2)))
  val out_data = Valid(new RawProducts(laneCount, magnitudeWidth))
}
