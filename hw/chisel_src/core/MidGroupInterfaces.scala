package dp.core

import dp.config._
import dp.pe._
import chisel3._
import chisel3.util._

/** Pure arithmetic and layout helpers shared by the five concrete MidGroups. */
object PETileMath {
  def resizeSInt(value: SInt, width: Int): SInt = {
    val out = Wire(SInt(width.W))
    if (value.getWidth > width) out := value.asUInt(width - 1, 0).asSInt
    else out := value.pad(width)
    out
  }

  /**
    * Historical precision-experiment helper, retained for SignificandTruncateSpec.
    * Not used by the current datapath. Clear fractional LSB positions toward zero.
    *
    * This differs from masking a two's-complement SInt: negative magnitudes
    * must be truncated before their sign is restored, otherwise the operation
    * rounds toward negative infinity and introduces a one-sided bias.
    */
  def clearLowBitsTowardZero(value: SInt, dropBits: Int): SInt = {
    val width = value.getWidth
    require(dropBits >= 0 && dropBits < width,
      s"fixed LSB drop $dropBits must be in [0,${width - 1}]")
    if (dropBits == 0) {
      resizeSInt(value, width)
    } else {
      // For x<0, adding 2^drop-1 before masking implements ceil(x/2^drop),
      // i.e. truncation toward zero. This needs one conditional narrow adder;
      // an abs -> mask -> restore-sign implementation would require two.
      val negative_bias = ((BigInt(1) << dropBits) - 1).S(width.W)
      val biased = Mux(value < 0.S, value + negative_bias, value)
      Cat(biased.asUInt(width - 1, dropBits), 0.U(dropBits.W)).asSInt
    }
  }

  /**
    * Put a signed fixed-point carrier at the MSB side of a wider add window.
    * This helper is deliberately widening-only: a MidGroup boundary must never
    * hide a precision-losing right shift, rounding operation, or truncation.
    */
  def placeAtAddTopExact(value: SInt, srcWidth: Int, dstWidth: Int): SInt = {
    require(srcWidth <= dstWidth, s"exact placement cannot narrow W$srcWidth to W$dstWidth")
    if (srcWidth == dstWidth) resizeSInt(value, dstWidth)
    else resizeSInt(value.pad(dstWidth) << (dstWidth - srcWidth), dstWidth)
  }

  /** Legal format/scale pair for one complete MidGroup transaction. */
  def legalDataScalePair(dataType: UInt, sfType: UInt): Bool =
    FormatCompat.legalDataScalePair(dataType, sfType)

  def legalABPair(aType: UInt, bType: UInt): Bool =
    FormatCompat.legalABPair(aType, bType)

  def canonicalProductType(aType: UInt, bType: UInt): UInt =
    FormatCompat.canonicalProductType(aType, bType)

  /** Scale slot selected by a PEGroup in a two- or four-group MidGroup. */
  def localScaleIndex(groupIndex: Int, dataType: UInt,
    groupCount: Int = MidGroupContract.groupCount): UInt = {
    require(groupCount == 2 || groupCount == MidGroupContract.groupCount)
    require(groupIndex >= 0 && groupIndex < groupCount)
    val indexWidth = log2Ceil(groupCount)
    Mux(
      dataType === DataType.nvfp4,
      groupIndex.U(indexWidth.W),
      Mux(dataType === DataType.e2_m1, (groupIndex / 2).U(indexWidth.W), 0.U(indexWidth.W))
    )
  }
}

object MidGroupContract {
  val groupCount: Int = 4
  val anchorWidth: Int = PEGroupContract.anchorWidth
  val carryBits: Int = log2Ceil(groupCount)

  def publicDataWidth(alignWidth: Int): Int = alignWidth + carryBits
}

/**
  * Atomic MidGroup result metadata.
  *
  * Every concrete MidGroup defines these fields as one numerical
  * transaction after its exact N0/N1 normalization boundary.
  */
class MidGroupOutput(dataWidth: Int) extends Bundle {
  val mid_magnitude = UInt((dataWidth - 1).W)
  val mid_negative = Bool()
  // LZD-corrected physical exponent of magnitude bit W-2.
  val mid_anchor = SInt(MidGroupContract.anchorWidth.W)
  val is_zero = Bool()
  val special = new SpecialValueFlags
}

class MidGroupIO(
  dimk: Int,
  numSF: Int,
  numG0: Int,
  numG1: Int,
  dataWidth: Int
) extends Bundle {
  val in_cfg = Input(new PETileConfig)
  val in_data = Flipped(Valid(new PEGroupInput(dimk, numSF, numG0, numG1)))
  val out_mid_data = Valid(new MidGroupOutput(dataWidth))
}

/**
  * IO-only shell. Concrete families own every datapath and pipeline register.
  * All MidGroups expose one common normalized data/anchor transaction.
  */
abstract class MidGroupBase(val alignWidth: Int = Design.dotCAddWidth, groupCount: Int = MidGroupContract.groupCount) extends Module {
  require(groupCount == 2 || groupCount == MidGroupContract.groupCount,
    s"MidGroup must contain 2 or 4 PEGroups, got $groupCount")
  final val groupSize: Int = Resource.groupDimK
  final val midGroupSize: Int = groupCount
  final val midDimk: Int = groupSize * midGroupSize
  final val midNumSF: Int = midGroupSize
  final val midNumG0: Int = midDimk
  final val midNumG1: Int = midDimk / 2
  final val anchorWidth: Int = MidGroupContract.anchorWidth
  final val outDataWidth: Int = MidGroupContract.publicDataWidth(alignWidth)

  require(alignWidth >= PEGroupFullContract.outputWidth,
    s"MidGroup W$alignWidth cannot hold the W${PEGroupFullContract.outputWidth} PEGroup boundary")

  val io = IO(new MidGroupIO(
    midDimk,
    midNumSF,
    midNumG0,
    midNumG1,
    outDataWidth
  ))
}
