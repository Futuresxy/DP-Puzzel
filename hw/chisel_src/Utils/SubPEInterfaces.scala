package dp.utils

import chisel3._
import chisel3.util._
import dp.config._

/** Fixed-point carrier layout. W = S + I + F. */
case class FixedLayout(signBits: Int, intBits: Int, fracBits: Int) {
  require(signBits >= 0 && intBits >= 0 && fracBits >= 0)
  val width: Int = signBits + intBits + fracBits
}

/** Full SubPE precision contract; exponent anchors are carried separately. */
object SubPEFixedPoint {
  // The W29 guard is retained for every Full format through PEGroup alignment.
  val defaultFullOutputWidth = Design.subpeOutWidth
  val defaultFP8RetainWidth = Design.subpeFP8RetainWidth

  val fp16_decoded = FixedLayout(0, 1, 11) // UQ1.11, low bit is decode padding
  val bf16_decoded = FixedLayout(0, 1, 7)  // UQ1.7
  val fp8_decoded = FixedLayout(0, 1, 3)   // UQ1.3

  // FP16 drops two known-zero product LSBs; BF16 appends six zeros to this layout.
  val high_product = FixedLayout(1, 2, 20)
  val fp8_lane_product = FixedLayout(1, 2, 6)
  val fp4_lane_product = FixedLayout(1, 6, 2) // E2M1/NVFP4 worst-case carrier
  val hif4_lane_product = FixedLayout(1, 4, 4)

  private def outputLayout(width: Int, intBits: Int): FixedLayout = {
    require(width > 1 + intBits, s"output width $width cannot hold S=1, I=$intBits")
    FixedLayout(1, intBits, width - 1 - intBits)
  }

  // Integer bits are fixed by the decoded mantissa range and local accumulation count.
  // Any wider SubPE carrier therefore contributes only additional fractional guard bits.
  def highOutput(width: Int): FixedLayout = outputLayout(width, intBits = 2)
  def fp8Output(width: Int): FixedLayout = outputLayout(width, intBits = 3)
  def fp4Output(width: Int): FixedLayout = outputLayout(width, intBits = 8)
  def hif4Output(width: Int): FixedLayout = outputLayout(width, intBits = 6)
}

/** Raw unsigned anchors for FP16/BF16 and individual FP8/FP6 products. */
object SubPEProductAnchor {
  // DataUnpack gives every finite nonzero operand an exponent >= 1, including
  // subnormals. Zero is thus below any live product's raw exponent sum (>= 2).
  // Mask before the first MAX: masking after local alignment cannot recover
  // small products already shifted away. NaN/Inf use a separate PG sideband.
  def apply(rawSum: UInt, aMant: UInt, bMant: UInt): UInt =
    Mux(aMant.orR && bMant.orR, rawSum, 0.U(rawSum.getWidth.W))
}

case class SubPEConfig(
  dimk: Int = 1,
  expWidth: Int = 10,
  mantWidth: Int = 16,
  subpeAnchorWidth: Int = 9,
  signGroupWidth: Int = 4,
  outWidth: Int = 29,
  fp8RetainWidth: Int = 28,
  precisionConfig: PEPrecisionConfig = Precision.hqe
) {
  require(dimk == 1, s"SubPEConfig dimk=$dimk must be 1 (one packed word)")
  require(expWidth > 0 && mantWidth > 0 && signGroupWidth > 0 && subpeAnchorWidth > 0,
    "SubPE input and anchor widths must be positive")
  val fp16ProductDroppedLsb: Int = 2
  val highPrecisionResultWidth: Int = SubPEFixedPoint.high_product.width
  val highPrecisionMagnitudeWidth: Int = highPrecisionResultWidth - 1
  val highPrecisionFracBits: Int = SubPEFixedPoint.high_product.fracBits
  val bf16ToFp16CarrierLsbZeros: Int = highPrecisionFracBits - 2 * SubPEFixedPoint.bf16_decoded.fracBits
  val fp8ProductSignedWidth: Int = SubPEFixedPoint.fp8_lane_product.width

  require(fp8RetainWidth >= fp8ProductSignedWidth, "fp8RetainWidth must hold one signed FP8/FP6 product")
  require(outWidth >= 2, s"outWidth must be >= 2 for ${precisionConfig.name}")

  def requireInputWidths(exp: Int, mant: Int, sign: Int, anchor: Int): Unit = {
    require(expWidth >= exp, s"${precisionConfig.name} SubPE expWidth=$expWidth must be >= $exp")
    require(mantWidth >= mant, s"${precisionConfig.name} SubPE mantWidth=$mantWidth must be >= $mant")
    require(signGroupWidth >= sign, s"${precisionConfig.name} SubPE signGroupWidth=$signGroupWidth must be >= $sign")
    require(subpeAnchorWidth >= anchor, s"${precisionConfig.name} SubPE subpeanchorWidth=$subpeAnchorWidth must be >= $anchor")
  }
}

/*  SubPE的输入接口配置
  * 目前仅支持同数据类型的点积计算，不支持混合精度计算
 */
class SubPEInput(cfg: SubPEConfig) extends Bundle {
  val a_exp   = UInt(cfg.expWidth.W)
  val b_exp   = UInt(cfg.expWidth.W)
  val ab_type = UInt(DataType.len.W)

  val a_mant  = UInt(cfg.mantWidth.W)
  val b_mant  = UInt(cfg.mantWidth.W)
  val a_sign  = UInt(cfg.signGroupWidth.W)
  val b_sign  = UInt(cfg.signGroupWidth.W)
}
/* SubPE numeric result. Format control remains at PEGroup level. */
class SubPEOutput(cfg: SubPEConfig) extends Bundle {
  val result = SInt(cfg.outWidth.W)
}
/* Early numeric exponent anchor; PEGroup owns the transaction dataType. */
class SubPEAnchor(cfg: SubPEConfig) extends Bundle {
  val subpe_anchor = UInt(cfg.subpeAnchorWidth.W)
}
abstract class SubPEBase(val cfg: SubPEConfig) extends Module {
  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new SubPEInput(cfg)))
    val out_data = Valid(new SubPEOutput(cfg))
    val out_anchor = Valid(new SubPEAnchor(cfg))
  })
}


object SubPEConfig {
  def forFamily(family: String, alignment: AlignmentConfig): SubPEConfig = {
    require(Set("HQE", "QE", "E")(family), "Dedicated H/Q arithmetic is implemented directly in PE_H/PE_Q")
    val capability = Precision.forFamily(family)
    family match {
      case "E" => SubPEConfig(expWidth = 1, mantWidth = 16, signGroupWidth = 4,
        subpeAnchorWidth = 2, outWidth = 11, fp8RetainWidth = alignment.qAlignWidth, precisionConfig = capability)
      case "HQE" | "QE" => SubPEConfig(expWidth = 10, mantWidth = 16, signGroupWidth = 4,
        subpeAnchorWidth = if (family == "HQE") 9 else 6, outWidth = alignment.qAlignWidth + 1,
        fp8RetainWidth = alignment.qAlignWidth, precisionConfig = capability)
    }
  }
}
