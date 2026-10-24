package dp.common

import chisel3._
import dp.config._

/** One packed operand. Low-index scalar elements occupy low word bits.
  * Scale slots: Q/HiF4 -> 0; MXFP4 -> word/8; NVFP4 -> word/4.
  */
class Operand(p: PEConfig) extends Bundle {
  val data = Vec(p.words, UInt(Parameters.wordBits.W))
  val scale = Vec(p.groups, UInt(8.W))
  val group0 = Vec(p.words, Bool())
  val group1 = Vec(p.words / 2, Bool())
}

class PEInput(p: PEConfig) extends Bundle {
  val a_format = UInt(Formats.width.W)
  val b_format = UInt(Formats.width.W)
  val a = new Operand(p)
  val b = new Operand(p)
}

/** NaN dominates; opposite signed infinities merge to canonical quiet NaN. */
class Special extends Bundle {
  val nan = Bool()
  val pos_inf = Bool()
  val neg_inf = Bool()
  def any: Bool = nan || pos_inf || neg_inf
}

object Special {
  def seen(nan: Bool, pos: Bool, neg: Bool): Special = {
    val flags = Wire(new Special)
    flags.nan := nan || (pos && neg)
    flags.pos_inf := !flags.nan && pos
    flags.neg_inf := !flags.nan && neg
    flags
  }
  def none: Special = seen(false.B, false.B, false.B)
  def merge(values: Seq[Special]): Special = {
    require(values.nonEmpty)
    seen(values.map(_.nan).reduce(_ || _), values.map(_.pos_inf).reduce(_ || _),
      values.map(_.neg_inf).reduce(_ || _))
  }
}

/** value = (-1)^negative * magnitude * 2^(anchor - (width-2)).
  * Nonzero magnitude is normalized to bit width-2. No FP32 rounding in PE.
  */
class DotResult(val dataWidth: Int) extends Bundle {
  val magnitude = UInt((dataWidth - 1).W)
  val negative = Bool()
  val anchor = SInt(Parameters.anchorWidth.W)
  val special = new Special
}

class AccControl extends Bundle {
  val c = UInt(32.W)
  val c_format = UInt(2.W)
  val rounding = UInt(3.W) // 0 RNE, 1 RTZ, 2 RDN, 3 RUP, 4 RMM
  val last = Bool()       // Opaque end-of-sequence marker; does not flush or stall.
}

class Result extends Bundle {
  val d = UInt(32.W)
  val last = Bool()
}
