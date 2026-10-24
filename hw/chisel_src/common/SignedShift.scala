package dp.common

import chisel3._
import chisel3.util.log2Ceil

/** Signed fixed-point shifts used by internal exponent alignment. */
object SignedShift {
  private def resizeSInt(value: SInt, width: Int): SInt = {
    val out = Wire(SInt(width.W))
    if (value.getWidth > width) {
      out := value.asUInt(width - 1, 0).asSInt
    } else {
      out := value.pad(width)
    }
    out
  }

  /**
    * Dynamic signed right shift with round-toward-zero (RTZ) semantics.
    *
    * RTZ(x, d) = (x >>> d) + (x < 0 && discarded bits are nonzero).
    * Call rightTowardZeroParts at a reduction boundary to absorb the correction
    * into the following sum instead of incrementing each wide shifted operand.
    */
  def rightTowardZero(value: SInt, shift: UInt): SInt =
    rightTowardZeroToWidth(value, shift, value.getWidth)

  def rightTowardZeroToWidth(value: SInt, shift: UInt, outWidth: Int): SInt = {
    val (floor, correction) = rightTowardZeroParts(value, shift, outWidth)
    resizeSInt(floor +& correction.asUInt.zext, outWidth)
  }

  /** Arithmetic barrel and one deferred RTZ correction in its output LSB.
    * Each selected barrel stage contributes the bits it discards to a sticky
    * OR. Shifts at or beyond the input width also handle the minimum signed
    * value exactly: a negative input produces floor=-1 and correction=1.
    */
  def rightTowardZeroParts(value: SInt, shift: UInt, outWidth: Int): (SInt, Bool) = {
    require(outWidth > 0, s"RTZ output width must be positive, got $outWidth")
    val width = value.getWidth
    require(width > 0 && shift.getWidth > 0)
    val stages = math.min(shift.getWidth, log2Ceil(width))
    var shifted = value
    var discarded = false.B
    for (stage <- 0 until stages) {
      val amount = 1 << stage
      val take = shift(stage)
      discarded = discarded || (take && shifted.asUInt(amount - 1, 0).orR)
      shifted = Mux(take, (shifted >> amount).pad(width), shifted)
    }
    // Large control bits all saturate the arithmetic result. Avoid building
    // redundant wide mux stages when exponent deltas have a wider carrier.
    if (shift.getWidth > stages) {
      val overWidth = shift(shift.getWidth - 1, stages).orR
      discarded = discarded || (overWidth && shifted.asUInt.orR)
      shifted = Mux(overWidth, Mux(value(width - 1), (-1).S(width.W), 0.S(width.W)), shifted)
    }
    (resizeSInt(shifted, outWidth), value(width - 1) && discarded)
  }

  /** RTZ inside the retained alignment window
  larger deltas contribute zero. */
  def rightTowardZeroLimited(
    value: SInt,
    shift: UInt,
    maxShift: Int,
    outWidth: Int
  ): SInt = {
    require(maxShift >= 0, s"RTZ maximum shift must be non-negative, got $maxShift")
    val compareWidth = math.max(shift.getWidth, math.max(1, chisel3.util.log2Ceil(maxShift + 2)))
    val over_window = shift.pad(compareWidth) > maxShift.U(compareWidth.W)
    Mux(over_window, 0.S(outWidth.W), rightTowardZeroToWidth(value, shift, outWidth))
  }
}
