package dp.utils

import chisel3._
import chisel3.util._
import dp.config._

/** Fixed-point coordinates that cross the current PEGroup/MidGroup boundary. */
object FixedPointMeta {
  val bpWidth = 6
  val scaleMantFracBits = 3
  val scaleMantProductWidth = 8

  private val defaultSubPECfg = SubPEConfig(
    expWidth = 10,
    mantWidth = 16,
    outWidth = Design.subpeOutWidth,
    fp8RetainWidth = Design.subpeFP8RetainWidth
  )

  /** Carrier paired with an anchor for magnitude bit W-2. */
  def topAnchoredLayout(dataWidth: Int): FixedLayout = {
    require(dataWidth >= 3, s"top-anchored width must be >=3, got $dataWidth")
    FixedLayout(1, 1, dataWidth - 2)
  }

  def sharedAlignedLayout(dataWidth: Int): FixedLayout = topAnchoredLayout(dataWidth)
  def midRawLayout(dataWidth: Int): FixedLayout = topAnchoredLayout(dataWidth)
  def midNormalizedLayout(dataWidth: Int): FixedLayout = topAnchoredLayout(dataWidth)

  private def pegroupFullOutputIntBitsValue(dataTypeCode: Int): Int =
    dataTypeCode match {
      case code if code == DataType.fp16.litValue.toInt  => 4
      case code if code == DataType.bf16.litValue.toInt  => 4
      case code if code == DataType.e5_m2.litValue.toInt  => 5
      case code if code == DataType.e4_m3.litValue.toInt  => 5
      case code if code == DataType.e3_m2.litValue.toInt  => 5
      case code if code == DataType.e2_m3.litValue.toInt  => 5
      case code if code == DataType.e2_m1.litValue.toInt  => 10
      case code if code == DataType.nvfp4.litValue.toInt => 13
      case code if code == DataType.hi_f4.litValue.toInt  => 11
      case _ => throw new IllegalArgumentException(
        s"unsupported Full PEGroup data type code $dataTypeCode"
      )
    }

  /** Current Full/Low/FP8 PEGroup boundary, W=S+I+F (W33 by default). */
  def pegroupFullOutputLayoutValue(dataTypeCode: Int, alignment: AlignmentConfig = AlignmentConfig()): FixedLayout = {
    val intBits = pegroupFullOutputIntBitsValue(dataTypeCode)
    FixedLayout(1, intBits, (alignment.qAlignWidth + 1 + alignment.groupGuardBits + 2) - 1 - intBits)
  }

  def pegroupFullOutputIntBits(dataType: UInt): UInt =
    MuxLookup(dataType, 1.U(bpWidth.W))(
      Seq(DataType.fp16, DataType.bf16, DataType.e5_m2, DataType.e4_m3,
        DataType.e3_m2, DataType.e2_m3, DataType.e2_m1, DataType.nvfp4, DataType.hi_f4)
        .map(t => t -> pegroupFullOutputIntBitsValue(t.litValue.toInt).U(bpWidth.W))
    )

  def subpeLayoutValue(
    dataTypeCode: Int,
    cfg: SubPEConfig = defaultSubPECfg
  ): FixedLayout = dataTypeCode match {
    case code if code == DataType.fp16.litValue.toInt  => SubPEFixedPoint.highOutput(cfg.outWidth)
    case code if code == DataType.bf16.litValue.toInt  => SubPEFixedPoint.highOutput(cfg.outWidth)
    case code if code == DataType.e5_m2.litValue.toInt  => SubPEFixedPoint.fp8Output(cfg.outWidth)
    case code if code == DataType.e4_m3.litValue.toInt  => SubPEFixedPoint.fp8Output(cfg.outWidth)
    case code if code == DataType.e3_m2.litValue.toInt  => SubPEFixedPoint.fp8Output(cfg.outWidth)
    case code if code == DataType.e2_m3.litValue.toInt  => SubPEFixedPoint.fp8Output(cfg.outWidth)
    case code if code == DataType.e2_m1.litValue.toInt  => SubPEFixedPoint.fp4Output(cfg.outWidth)
    case code if code == DataType.nvfp4.litValue.toInt => SubPEFixedPoint.fp4Output(cfg.outWidth)
    case code if code == DataType.hi_f4.litValue.toInt  => SubPEFixedPoint.hif4Output(cfg.outWidth)
    case _ => throw new IllegalArgumentException(
      s"unsupported SubPE fixed-point data type code $dataTypeCode"
    )
  }

  /** Exact MSB-side placement adds only fractional positions. */
  def formatRelativePlacedLayout(source: FixedLayout, placedWidth: Int): FixedLayout = {
    require(source.signBits == 1,
      s"format-relative placement requires one sign bit, got ${source.signBits}")
    require(placedWidth >= source.width,
      s"exact placement cannot narrow W${source.width} to W$placedWidth")
    FixedLayout(source.signBits, source.intBits,
      source.fracBits + placedWidth - source.width)
  }

  def dataBias2xValue(dataTypeCode: Int): Int = dataTypeCode match {
    case code if code == DataType.fp16.litValue.toInt  => 2 * FPBias.fp16Bias
    case code if code == DataType.bf16.litValue.toInt  => 2 * FPBias.bf16Bias
    case code if code == DataType.e5_m2.litValue.toInt  => 2 * FPBias.e5Bias
    case code if code == DataType.e4_m3.litValue.toInt  => 2 * FPBias.e5Bias
    case code if code == DataType.e3_m2.litValue.toInt  => 2 * FPBias.e5Bias
    case code if code == DataType.e2_m3.litValue.toInt  => 2 * FPBias.e5Bias
    case code if code == DataType.e2_m1.litValue.toInt  => 0
    case code if code == DataType.nvfp4.litValue.toInt => 0
    case code if code == DataType.hi_f4.litValue.toInt  => 0
    case _ => throw new IllegalArgumentException(
      s"unsupported fixed-point data type code $dataTypeCode"
    )
  }

  def dataBias2x(dataType: UInt, anchorWidth: Int): SInt = {
    require(anchorWidth >= 9,
      s"anchor width must represent BF16 bias2x=254, got W$anchorWidth")
    MuxLookup(dataType, 0.S(anchorWidth.W))(
      Seq(DataType.fp16, DataType.bf16, DataType.e5_m2,
        DataType.e4_m3, DataType.e3_m2, DataType.e2_m3)
        .map(t => t -> dataBias2xValue(t.litValue.toInt).S(anchorWidth.W))
    )
  }

  private def resizeSInt(value: SInt, width: Int): SInt = {
    val out = Wire(SInt(width.W))
    if (value.getWidth > width) out := value.asUInt(width - 1, 0).asSInt
    else out := value.pad(width)
    out
  }

  /** Host-side constant shared by each family's raw-anchor coordinate. */
  def pegroupFullTopAnchorOffsetValue(dataTypeCode: Int): Int =
    -dataBias2xValue(dataTypeCode) + pegroupFullOutputIntBitsValue(dataTypeCode) - 1

  /** rawAnchor - 2*bias + I - 1: exponent of PEGroup magnitude bit W-2. */
  def pegroupFullRawAnchorToTopValue(
    rawAnchor: BigInt,
    dataTypeCode: Int
  ): BigInt = rawAnchor + pegroupFullTopAnchorOffsetValue(dataTypeCode)

  def pegroupFullRawAnchorToTop(
    rawAnchor: SInt,
    dataType: UInt,
    assertEnable: Bool
  ): SInt = {
    val anchorWidth = PEGroupContract.anchorWidth
    require(rawAnchor.getWidth == anchorWidth)
    val calcWidth = anchorWidth + 2
    val converted = rawAnchor.pad(calcWidth) -
      dataBias2x(dataType, anchorWidth).pad(calcWidth) +
      pegroupFullOutputIntBits(dataType).zext.pad(calcWidth) -
      1.S(calcWidth.W)
    val result = resizeSInt(converted, anchorWidth)
    when(assertEnable) {
      assert(converted === result.pad(calcWidth),
        "Full PEGroup raw-to-top anchor overflow")
    }
    result
  }

  def midRawTopAnchorValue(groupTopAnchor: BigInt, fanIn: Int): BigInt = {
    require(fanIn > 0)
    groupTopAnchor + log2Ceil(fanIn)
  }

  def midRawTopAnchor(
    sharedTopAnchor: SInt,
    fanIn: Int,
    anchorWidth: Int,
    assertEnable: Bool
  ): SInt = {
    require(sharedTopAnchor.getWidth == anchorWidth && fanIn > 0)
    val calcWidth = anchorWidth + 1
    val wide = sharedTopAnchor.pad(calcWidth) + log2Ceil(fanIn).S(calcWidth.W)
    val result = resizeSInt(wide, anchorWidth)
    when(assertEnable) {
      assert(wide === result.pad(calcWidth), "MidGroup raw top-anchor overflow")
    }
    result
  }

  def normalizedTopAnchorValue(rawTopAnchor: BigInt, leadingZeros: Int): BigInt = {
    require(leadingZeros >= 0)
    rawTopAnchor + 1 - leadingZeros
  }

  def normalizedTopAnchor(
    rawTopAnchor: SInt,
    leadingZeros: UInt,
    assertEnable: Bool
  ): SInt = {
    val anchorWidth = rawTopAnchor.getWidth
    val calcWidth = anchorWidth + 2
    val wide = rawTopAnchor.pad(calcWidth) + 1.S(calcWidth.W) -
      leadingZeros.zext.pad(calcWidth)
    val result = resizeSInt(wide, anchorWidth)
    when(assertEnable) {
      assert(wide === result.pad(calcWidth), "normalized top-anchor overflow")
    }
    result
  }
}
