package dp.core

import chisel3._
import chisel3.util._
import dp.config._
import dp.common._

/** Inline common C/D path for both architectural tops.
  * D = sum(selected PE dots) + C. C is an explicit input, never a hidden feedback register.
  * Dots arrive at S11, output at S18; no cross-transaction accumulation or backpressure.
  */
object Accumulate {
  def apply(dots: Seq[DotResult], control: AccControl, inputValid: Bool, width: Int): ValidIO[Result] = {
    require(dots.nonEmpty && dots.size <= Parameters.maxKPEs && dots.forall(_.dataWidth == width))
    val valid = (1 to Parameters.resultLatency - 2).scanLeft(inputValid) { (previous, stage) =>
      RegNext(previous, false.B).suggestName(s"acc_s${stage}_valid_q")
    }
    when(inputValid) {
      assert(control.c_format <= Formats.cBf16, "C must be FP32, FP16 or BF16")
      assert(control.rounding <= 4.U, "Rounding must be RNE, RTZ, RDN, RUP or RMM")
    }
    val raw_c = Arithmetic.delay(control.c, inputValid, 9, "c_raw_s9")
    val c_format = Arithmetic.delay(control.c_format, inputValid, 9, "c_format_s9")
    val s10_c_q = RegEnable(Decode.c(raw_c, c_format), valid(9))
    val zeros = Arithmetic.leadingZeros(s10_c_q.magnitude)
    val normalized = (s10_c_q.magnitude << zeros)(23, 0)
    val c = Wire(new DotResult(width))
    c.magnitude := Cat(normalized, 0.U((width - 25).W))
    c.negative := s10_c_q.negative
    c.anchor := Mux(s10_c_q.magnitude.orR, s10_c_q.anchor - zeros.zext, (-1024).S)
    c.special := s10_c_q.special
    val s11_c_q = RegEnable(c, valid(10))
    val terms = dots :+ s11_c_q
    val anchors = terms.map(t => Mux(t.magnitude.orR, t.anchor, (-1024).S(11.W)))
    val (maximum, winner) = Arithmetic.maximum(anchors)
    val top = Mux(maximum === (-1024).S, 0.S(11.W), maximum)
    val s12_magnitude_q = RegEnable(VecInit(terms.map(_.magnitude)), valid(11))
    val s12_negative_q = RegEnable(VecInit(terms.map(_.negative)), valid(11))
    val s12_shift_q = RegEnable(VecInit(anchors.map(Arithmetic.delta(top, _, width))), valid(11))
    val s12_winner_q = RegEnable(winner, valid(11))
    val s12_anchor_q = RegEnable(top, valid(11))

    // Align unsigned magnitudes, then apply signs: exactly signed RTZ without abs logic.
    val aligned = (0 until terms.size).map { slot =>
      if (slot == 0) Arithmetic.signed(s12_magnitude_q(s12_winner_q), s12_negative_q(s12_winner_q))
      else {
        val swap = s12_winner_q === slot.U
        val magnitude = Mux(swap, s12_magnitude_q(0), s12_magnitude_q(slot))
        val shift = Mux(swap, s12_shift_q(0), s12_shift_q(slot))
        val negative = Mux(swap, s12_negative_q(0), s12_negative_q(slot))
        Arithmetic.signed(magnitude >> shift, negative)
      }
    }
    val s13_aligned_q = RegEnable(VecInit(aligned), valid(12))
    val s13_anchor_q = RegEnable(s12_anchor_q, valid(12))
    val sumWidth = width + log2Ceil(terms.size)
    val s14_sum_q = RegEnable(Arithmetic.sum(s13_aligned_q.toSeq, sumWidth), valid(13))
    val s14_anchor_q = RegEnable(s13_anchor_q + log2Ceil(terms.size).S, valid(13))
    val s14_special_q = Arithmetic.delay(Special.merge(terms.map(_.special)), valid(11), 3, "special_s14")
    val s14_rounding_q = Arithmetic.delay(control.rounding, inputValid, 14, "rounding_s14")
    val s14_last_q = Arithmetic.delay(control.last, inputValid, 14, "last_s14")
    val prepared = Normalize.forFp32(s14_sum_q, s14_anchor_q, s14_special_q,
      s14_rounding_q, s14_last_q, valid(14))
    val pack = Module(new Fp32Pack)
    pack.io.in.valid := valid(16)
    pack.io.in.bits := prepared
    pack.io.out
  }
}
