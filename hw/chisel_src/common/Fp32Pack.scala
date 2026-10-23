package dp.common

import chisel3._
import chisel3.util._

/** Two-cycle FP32 rounding/packing primitive, no stall or external FPU dependency.
  * Supports gradual underflow, overflow, canonical NaN, RNE/RTZ/RDN/RUP/RMM.
  * Rounds the finite-window sum supplied by the caller, not an exact dot product.
  */
class Fp32Pack extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Valid(new RoundInput))
    val out = Valid(new Result)
  })
  val bits = io.in.bits
  when(io.in.valid) { assert(bits.rounding <= 4.U, "Unsupported rounding mode") }

  // Denormalize before rounding; discarded bits are folded into the sticky bit.
  val underflow = bits.exponent < (-126).S
  val distance = Mux(underflow, ((-126).S(13.W) - bits.exponent.pad(13)).asUInt, 0.U)
  val (shifted, sticky) = Arithmetic.shiftSticky(bits.magnitude, distance)
  val mantissa = Cat(shifted(25, 1), shifted(0) || sticky)
  val retained = mantissa(25, 2)
  val guard = mantissa(1)
  val tail = mantissa(0)
  val inexact = guard || tail
  val increment = MuxLookup(bits.rounding, false.B)(Seq(
    0.U -> (guard && (tail || retained(0))),
    1.U -> false.B,
    2.U -> (bits.negative && inexact),
    3.U -> (!bits.negative && inexact),
    4.U -> guard))
  val rounded = retained +& increment.asUInt
  val carry = rounded(24)
  val biased = bits.exponent.pad(13) + 127.S + carry.asUInt.zext
  val overflow = !underflow && biased >= 255.S
  val toward_finite = bits.rounding === 1.U ||
    (bits.rounding === 2.U && !bits.negative) || (bits.rounding === 3.U && bits.negative)

  // S17 ends after shifting/rounding; S18 contains only encoding and special selection.
  val s1_valid_q = RegNext(io.in.valid, false.B)
  val s1_sign_q = RegEnable(bits.negative, io.in.valid)
  val s1_exponent_q = RegEnable(biased, io.in.valid)
  val s1_fraction_q = RegEnable(Mux(carry, 0.U(23.W), rounded(22, 0)), io.in.valid)
  val s1_sub_carry_q = RegEnable(rounded(23), io.in.valid)
  val s1_underflow_q = RegEnable(underflow, io.in.valid)
  val s1_overflow_q = RegEnable(overflow, io.in.valid)
  val s1_toward_finite_q = RegEnable(toward_finite, io.in.valid)
  val s1_special_q = RegEnable(bits.special, io.in.valid)
  val s1_zero_q = RegEnable(!bits.magnitude.orR, io.in.valid)
  val s1_last_q = RegEnable(bits.last, io.in.valid)

  val normal = Cat(s1_sign_q, s1_exponent_q.asUInt(7, 0), s1_fraction_q)
  // A subnormal rounding up to bit 23 becomes the smallest normal.
  val subnormal = Cat(s1_sign_q, Mux(s1_sub_carry_q, 1.U(8.W), 0.U(8.W)), s1_fraction_q)
  val overflow_value = Cat(s1_sign_q, Mux(s1_toward_finite_q, 254.U(8.W), 255.U(8.W)),
    Mux(s1_toward_finite_q, Fill(23, 1.U(1.W)), 0.U(23.W)))
  val finite = Mux(s1_overflow_q, overflow_value, Mux(s1_underflow_q, subnormal, normal))
  val packed = MuxCase(finite, Seq(
    s1_special_q.nan -> "h7fc00000".U(32.W),
    s1_special_q.pos_inf -> "h7f800000".U(32.W),
    s1_special_q.neg_inf -> "hff800000".U(32.W),
    s1_zero_q -> 0.U(32.W)))
  val s2_valid_q = RegNext(s1_valid_q, false.B)
  io.out.valid := s2_valid_q
  io.out.bits.d := RegEnable(packed, s1_valid_q)
  io.out.bits.last := RegEnable(s1_last_q, s1_valid_q)
}
