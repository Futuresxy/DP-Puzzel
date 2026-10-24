package dp.core

import dp.config._
import dp.common.BalancedLeadingZero
import chisel3._
import chisel3.util._

/** Fixed C-side carrier used by PETile before the final dot+C alignment. */
object CUnpackContract {
  val magnitudeWidth: Int = 24
  val carrierWidth: Int = magnitudeWidth + 1
  val anchorWidth: Int = Design.roundExpWidth
}

/** Batch control is attached to each synchronous AB+C transaction. */
class CUnpackerInput extends Bundle {
  val c = UInt(32.W)
  val c_type = UInt(CDataType.len.W)
  val rm = UInt(3.W)
  val out_type = UInt(3.W)
  val last = Bool()
}

/**
  * Losslessly normalized C token.
  *
  * `topAnchor` is the exponent of magnitude bit MagnitudeWidth-1. The
  * independent sign and magnitude have equivalent S-I-F = 1-1-23, matching
  * the normalized MidGroup anchor convention without a two's-complement
  * conversion: value = (-1)^negative * magnitude * 2^(topAnchor - 23).
  */
class CUnpackerOutput extends Bundle {
  val magnitude = UInt(CUnpackContract.magnitudeWidth.W)
  val negative = Bool()
  val top_anchor = SInt(CUnpackContract.anchorWidth.W)
  val is_zero = Bool()
  val special = new SpecialValueFlags
  val rm = UInt(3.W)
  val out_type = UInt(3.W)
  val last = Bool()
}

/**
  * Two-stage forward-only C decoder and exact normalizer.
  *
  * U0 decodes FP32/FP16/BF16 into a common W24 magnitude and independent
  * sign. U1 performs leading-zero count, exact normalization, and top-anchor
  * correction directly on the magnitude. No rounding or packing occurs here.
  */
class CUnpacker extends Module {
  private val magnitudeWidth = CUnpackContract.magnitudeWidth
  private val anchorWidth = CUnpackContract.anchorWidth
  private val zero_anchor = (-(BigInt(1) << (anchorWidth - 1))).S(anchorWidth.W)

  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new CUnpackerInput))
    val out_data = Valid(new CUnpackerOutput)
  })

  private def unpackFloat(
    data: UInt,
    expHi: Int,
    expLo: Int,
    mantHi: Int,
    mantLo: Int,
    bias: Int,
    sourceMagnitudeWidth: Int
  ): (SInt, UInt) = {
    val raw_exp = data(expHi, expLo)
    val denormal = raw_exp === 0.U
    val exponent = Mux(
      denormal,
      (1 - bias).S(anchorWidth.W),
      (raw_exp.zext - bias.S).pad(anchorWidth)
    )
    val magnitude = Cat(!denormal, data(mantHi, mantLo))
    val pad = magnitudeWidth - sourceMagnitudeWidth
    require(pad >= 0,
      s"C source magnitude W$sourceMagnitudeWidth exceeds W$magnitudeWidth")
    val aligned_magnitude = if (pad == 0) magnitude else Cat(magnitude, 0.U(pad.W))
    (exponent, aligned_magnitude)
  }

  private val (fp32_exp, fp32_magnitude) =
    unpackFloat(io.in_data.bits.c, 30, 23, 22, 0, FPBias.fp32Bias, 24)
  private val (fp16_exp, fp16_magnitude) =
    unpackFloat(io.in_data.bits.c, 14, 10, 9, 0, FPBias.fp16Bias, 11)
  private val (bf16_exp, bf16_magnitude) =
    unpackFloat(io.in_data.bits.c, 14, 7, 6, 0, FPBias.bf16Bias, 8)

  private def classifyFloat(
    data: UInt,
    signBit: Int,
    expHi: Int,
    expLo: Int,
    mantHi: Int,
    mantLo: Int
  ): (Bool, Bool, Bool) = {
    val raw_exp = data(expHi, expLo)
    val raw_mant = data(mantHi, mantLo)
    val exp_all_ones = raw_exp.andR
    val is_nan = exp_all_ones && raw_mant.orR
    val is_inf = exp_all_ones && !raw_mant.orR
    (is_nan, is_inf, data(signBit))
  }

  private val fp32_class = classifyFloat(io.in_data.bits.c, 31, 30, 23, 22, 0)
  private val fp16_class = classifyFloat(io.in_data.bits.c, 15, 14, 10, 9, 0)
  private val bf16_class = classifyFloat(io.in_data.bits.c, 15, 14, 7, 6, 0)

  // U0: common C decode register.
  private val s10_valid_q = RegNext(io.in_data.valid, false.B)
  private val s10_exp_q = Reg(SInt(anchorWidth.W))
  private val s10_magnitude_q = Reg(UInt(magnitudeWidth.W))
  private val s10_negative_q = Reg(Bool())
  private val s10_special_q = Reg(new SpecialValueFlags)
  private val s10_rm_q = Reg(UInt(3.W))
  private val s10_out_type_q = Reg(UInt(3.W))
  private val s10_last_q = Reg(Bool())

  // U1: normalized token register.
  private val s11_valid_q = RegNext(s10_valid_q, false.B)
  private val s11_bits_q = Reg(new CUnpackerOutput)
  io.out_data.valid := s11_valid_q
  io.out_data.bits := s11_bits_q

  private val selected_exp = WireDefault(0.S(anchorWidth.W))
  private val selected_magnitude = WireDefault(0.U(magnitudeWidth.W))
  private val selected_na_n = WireDefault(false.B)
  private val selected_inf = WireDefault(false.B)
  private val selected_sign = WireDefault(false.B)
  switch(io.in_data.bits.c_type) {
    is(CDataType.fp32) {
      selected_exp := fp32_exp
      selected_magnitude := fp32_magnitude
      selected_na_n := fp32_class._1
      selected_inf := fp32_class._2
      selected_sign := fp32_class._3
    }
    is(CDataType.fp16) {
      selected_exp := fp16_exp
      selected_magnitude := fp16_magnitude
      selected_na_n := fp16_class._1
      selected_inf := fp16_class._2
      selected_sign := fp16_class._3
    }
    is(CDataType.bf16) {
      selected_exp := bf16_exp
      selected_magnitude := bf16_magnitude
      selected_na_n := bf16_class._1
      selected_inf := bf16_class._2
      selected_sign := bf16_class._3
    }
  }
  private val selected_special = SpecialValueFlags.fromSeen(
    selected_na_n,
    selected_inf && !selected_sign,
    selected_inf && selected_sign
  )

  when(io.in_data.valid) {
    locally {
      s10_exp_q := Mux(selected_special.any, 0.S(anchorWidth.W), selected_exp)
      s10_magnitude_q := Mux(selected_special.any, 0.U, selected_magnitude)
      s10_negative_q := selected_sign && !selected_special.any
      s10_special_q := selected_special
      s10_rm_q := io.in_data.bits.rm
      s10_out_type_q := io.in_data.bits.out_type
      s10_last_q := io.in_data.bits.last
    }
  }

  private val is_zero = s10_magnitude_q === 0.U
  private val leadingZeros = BalancedLeadingZero.count(s10_magnitude_q)
  private val shifted_magnitude = s10_magnitude_q << leadingZeros
  private val normalized_magnitude = shifted_magnitude(magnitudeWidth - 1, 0)
  // LZD counts only magnitude bits: a normal input already has LZC=0.
  private val corrected_anchor_wide =
    s10_exp_q.pad(anchorWidth + 2) -
      leadingZeros.zext.pad(anchorWidth + 2)
  private val corrected_anchor = PETileMath.resizeSInt(corrected_anchor_wide, anchorWidth)

  when(s10_valid_q) {
    locally {
      when(!is_zero) {
        assert(normalized_magnitude(magnitudeWidth - 1),
          "nonzero C must normalize its leading one to the carrier top bit")
        assert(corrected_anchor_wide === corrected_anchor.pad(anchorWidth + 2),
          "normalized C top-anchor overflow")
      }
      s11_bits_q.magnitude := Mux(is_zero, 0.U, normalized_magnitude)
      // Preserve the existing canonical +0 numeric lane, including specials.
      s11_bits_q.negative := !is_zero && s10_negative_q
      s11_bits_q.top_anchor := Mux(is_zero, zero_anchor, corrected_anchor)
      s11_bits_q.is_zero := is_zero
      s11_bits_q.special := s10_special_q
      s11_bits_q.rm := s10_rm_q
      s11_bits_q.out_type := s10_out_type_q
      s11_bits_q.last := s10_last_q
    }
  }
}
