package dp.config

import chisel3._

/** Runtime format compatibility shared by PETile, MidGroup, and DataUnpack. */
object FormatCompat {
  def isHighPrecision(dataType: UInt): Bool =
    dataType === DataType.fp16 || dataType === DataType.bf16

  def isFP8FP6(dataType: UInt): Bool =
    dataType === DataType.e5_m2 || dataType === DataType.e4_m3 ||
      dataType === DataType.e3_m2 || dataType === DataType.e2_m3

  def isInterleavableFP4(dataType: UInt): Bool =
    dataType === DataType.e2_m1 || dataType === DataType.nvfp4

  def isHiF4(dataType: UInt): Bool = dataType === DataType.hi_f4

  /** One operand's architected element/scale pairing. */
  def legalDataScalePair(dataType: UInt, sfType: UInt): Bool = {
    val high = isHighPrecision(dataType)
    val fp8fp6 = isFP8FP6(dataType)
    (high && (sfType === MX.none || sfType === MX.e8_m0)) ||
      ((fp8fp6 || dataType === DataType.e2_m1) && sfType === MX.e8_m0) ||
      (dataType === DataType.nvfp4 && sfType === MX.e4_m3) ||
      (dataType === DataType.hi_f4 && sfType === MX.e6_m2)
  }

  /**
    * Legal A/B element pairing after independent unpack.
    *
    * FP8/FP6 all become the same two-lane E5M3 carrier. MXFP4 and NVFP4
    * share the same four-lane E2M1 carrier. High precision and HiF4 retain
    * their same-type instruction-level contracts.
    */
  def legalABPair(aType: UInt, bType: UInt): Bool = {
    val same_high = isHighPrecision(aType) && aType === bType
    val fp8fp6 = isFP8FP6(aType) && isFP8FP6(bType)
    val fp4 = isInterleavableFP4(aType) && isInterleavableFP4(bType)
    val same_hi_f4 = isHiF4(aType) && isHiF4(bType)
    same_high || fp8fp6 || fp4 || same_hi_f4
  }

  /**
    * Canonical product family used only after both operands have been unpacked.
    * A mixed E2M1/NVFP4 product uses the NVFP4 fixed-point coordinate because
    * one fractional E4M3 scale mantissa is present.
    */
  def canonicalProductType(aType: UInt, bType: UInt): UInt = Mux(
    isHighPrecision(aType),
    aType,
    Mux(
      isFP8FP6(aType) && isFP8FP6(bType),
      DataType.e5_m2,
      Mux(
        isInterleavableFP4(aType) && isInterleavableFP4(bType),
        Mux(aType === DataType.nvfp4 || bType === DataType.nvfp4,
          DataType.nvfp4, DataType.e2_m1),
        DataType.hi_f4
      )
    )
  )

  /** Packed active-lane mask for one 16-bit input word. */
  def laneMask(dataType: UInt, width: Int): UInt = {
    require(width > 0)
    val one_lane = 1.U(width.W)
    val two_lanes = ((BigInt(1) << math.min(width, 2)) - 1).U(width.W)
    val four_lanes = ((BigInt(1) << math.min(width, 4)) - 1).U(width.W)
    Mux(isHighPrecision(dataType), one_lane,
      Mux(isFP8FP6(dataType), two_lanes,
        Mux(isInterleavableFP4(dataType) || isHiF4(dataType), four_lanes, 0.U)))
  }
}

/** Canonical special-value state for an additive reduction. */
class SpecialValueFlags extends Bundle {
  val is_nan = Bool()
  val is_pos_inf = Bool()
  val is_neg_inf = Bool()

  def any: Bool = is_nan || is_pos_inf || is_neg_inf
}

object SpecialValueFlags {
  /** Canonicalize NaN and opposite-sign infinity precedence. */
  def fromSeen(nanSeen: Bool, posInfSeen: Bool, negInfSeen: Bool): SpecialValueFlags = {
    val out = Wire(new SpecialValueFlags)
    val invalid = nanSeen || (posInfSeen && negInfSeen)
    out.is_nan := invalid
    out.is_pos_inf := !invalid && posInfSeen
    out.is_neg_inf := !invalid && negInfSeen
    out
  }

  /** IEEE-style additive merge: NaN/opposite infinities dominate one infinity. */
  def mergeAdd(values: Seq[SpecialValueFlags]): SpecialValueFlags = {
    require(values.nonEmpty, "special-value merge requires at least one input")
    fromSeen(
      values.map(_.is_nan).reduce(_ || _),
      values.map(_.is_pos_inf).reduce(_ || _),
      values.map(_.is_neg_inf).reduce(_ || _)
    )
  }

  def none: SpecialValueFlags = fromSeen(false.B, false.B, false.B)
}
