package dp.utils

import dp.config._
import chisel3._
import chisel3.util._

object PEContract {
  val groupCount = 4
  val anchorWidth = 11
  def publicDataWidth(alignWidth: Int): Int = alignWidth + 2
}

/** Atomic top-anchored result: value = (-1)^negative * magnitude * 2^(top_anchor-F).
  * Public F=alignment.peAlignWidth, for every family and g2/g4.
  */
class PEDotResult(dataWidth: Int) extends Bundle {
  val magnitude = UInt((dataWidth - 1).W)
  val negative = Bool()
  val top_anchor = SInt(PEContract.anchorWidth.W)
  val is_zero = Bool()
  val special = new SpecialValueFlags
}
class PEIO(wordCount: Int, groupCount: Int, resultWidth: Int) extends Bundle {
  val in_cfg = Input(new PETileConfig)
  val in_data = Flipped(Valid(new PEGroupInput(wordCount, groupCount, wordCount, wordCount / 2)))
  val out_data = Valid(new PEDotResult(resultWidth))
}

/** IO-only base; each PE owns its arithmetic/pipeline, optionally retaining PGs. */
abstract class PEBase(val config: PEConfig, val alignment: AlignmentConfig) extends Module {
  val wordCount: Int = config.wordCount
  val groupCount: Int = config.groupCount
  val io = IO(new PEIO(wordCount, groupCount, alignment.peResultWidth))
}

object PEMath {
  def resizeSInt(value: SInt, width: Int): SInt = {
    val out = Wire(SInt(width.W))
    out := (if (value.getWidth > width) value.asUInt(width - 1, 0).asSInt else value.pad(width))
    out
  }
}
