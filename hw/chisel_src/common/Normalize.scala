package dp.common

import chisel3._
import chisel3.util._
import dp.config.Parameters

class RoundInput extends Bundle {
  val magnitude = UInt(26.W) // hidden, 23 fraction, guard, sticky
  val negative = Bool()
  val exponent = SInt(Parameters.anchorWidth.W)
  val special = new Special
  val rounding = UInt(3.W)
  val last = Bool()
}

/** Inline two-cycle normalizers. The PE boundary is exact; final FP32 preparation jams tails. */
object Normalize {
  def exact(sum: SInt, anchor: SInt, special: Special, valid: Bool, outWidth: Int): DotResult = {
    val width = sum.getWidth
    require(outWidth >= width)
    val wide = sum.pad(width + 1)
    val magnitude = Mux(wide < 0.S, -wide, wide).asUInt(width - 1, 0)
    val magnitude_q = RegEnable(magnitude, valid)
    val negative_q = RegEnable(sum < 0.S, valid)
    val zeros_q = RegEnable(Arithmetic.leadingZeros(magnitude), valid)
    val anchor_q = RegEnable(anchor, valid)
    val special_q = RegEnable(special, valid)
    val valid_q = RegNext(valid, false.B)

    val left = Mux(zeros_q === 0.U, 0.U, zeros_q - 1.U)
    val shifted = magnitude_q << left
    // LZC=0 occurs only at minimum SInt; its magnitude is a power of two.
    val normalized = Mux(zeros_q === 0.U, magnitude_q(width - 1, 1), shifted(width - 2, 0))
    val bits = Wire(new DotResult(outWidth))
    bits.magnitude := (if (outWidth == width) normalized else Cat(normalized, 0.U((outWidth - width).W)))
    bits.negative := negative_q && magnitude_q.orR
    bits.anchor := Mux(magnitude_q.orR, anchor_q + 1.S - zeros_q.zext, (-1024).S)
    bits.special := special_q
    RegEnable(bits, valid_q)
  }

  def forFp32(sum: SInt, anchor: SInt, special: Special, rounding: UInt,
    last: Bool, valid: Bool): RoundInput = {
    val width = sum.getWidth
    require(width >= 26)
    val wide = sum.pad(width + 1)
    val magnitude = Mux(wide < 0.S, -wide, wide).asUInt(width - 1, 0)
    val magnitude_q = RegEnable(magnitude, valid)
    val negative_q = RegEnable(sum < 0.S, valid)
    val zeros_q = RegEnable(Arithmetic.leadingZeros(magnitude), valid)
    val anchor_q = RegEnable(anchor, valid)
    val special_q = RegEnable(special, valid)
    val rounding_q = RegEnable(rounding, valid)
    val last_q = RegEnable(last, valid)
    val valid_q = RegNext(valid, false.B)
    val normalized = (magnitude_q << zeros_q)(width - 1, 0)
    val bits = Wire(new RoundInput)
    bits.magnitude := Cat(normalized(width - 1, width - 25), normalized(width - 26, 0).orR)
    bits.negative := negative_q && magnitude_q.orR
    bits.exponent := Mux(magnitude_q.orR, anchor_q + 1.S - zeros_q.zext, 0.S)
    bits.special := special_q
    bits.rounding := rounding_q
    bits.last := last_q
    RegEnable(bits, valid_q)
  }
}
