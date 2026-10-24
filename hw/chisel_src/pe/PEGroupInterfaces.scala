package dp.pe

import chisel3._
import chisel3.util._
import dp.config.{DataType, SpecialValueFlags}
import dp.core.VectorInputBundle

/** Packed A/B input consumed by every concrete PEGroup family. */
class PEGroupInput(dimk: Int, numSF: Int, numG0: Int, numG1: Int) extends Bundle {
  val a = new VectorInputBundle(dimk, numSF, numG0, numG1)
  val b = new VectorInputBundle(dimk, numSF, numG0, numG1)
}

/** Fixed-point group result and its additive special-value classification. */
class PEGroupOutput(outputWidth: Int) extends Bundle {
  val mul_scale_mant = SInt(outputWidth.W)
  val special = new SpecialValueFlags
}

/** Early numeric group anchor. The transaction format is owned by MidGroup cfg. */
class PEGroupAnchor(anchorWidth: Int) extends Bundle {
  val pegroup_anchor = SInt(anchorWidth.W)
}

private[pe] class PEGroupShiftConfig(dimk: Int, shiftWidth: Int) extends Bundle {
  val shifts = Vec(dimk, UInt(shiftWidth.W))
}

/**
  * Common PEGroup shell.
  *
  * This base class intentionally contains only the external interface and
  * shape checks.  Each family owns its complete C0-C7 datapath so reviewing or
  * optimizing one family cannot silently change another family.
  */
abstract class PEGroupBase(
  val dimk: Int,
  val numSF: Int,
  val numG0: Int,
  val numG1: Int,
  val outputWidth: Int
) extends Module {
  require(numSF == 1, s"PEGroup supports exactly one scale factor, got numSF=$numSF")
  require(numG0 == dimk, s"PEGroup expects numG0 == dimk, got $numG0 != $dimk")
  require((numG0 % 2) == 0, s"PEGroup expects even numG0, got $numG0")
  require(numG1 == numG0 / 2, s"PEGroup expects numG1 == numG0/2, got $numG1")
  require(outputWidth > 0, s"PEGroup output width must be positive, got $outputWidth")

  final val anchorWidth: Int = PEGroupContract.anchorWidth

  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new PEGroupInput(dimk, numSF, numG0, numG1)))
    val out_pegroup_anchor = Valid(new PEGroupAnchor(anchorWidth))
    val out_pegroup_data = Valid(new PEGroupOutput(outputWidth))
  })
}
