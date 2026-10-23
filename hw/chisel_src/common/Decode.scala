package dp.common

import chisel3._
import chisel3.util._
import dp.config._

class DecodedWord(p: PEConfig) extends Bundle {
  val exponent = UInt(p.exponentWidth.W)
  val mantissa = UInt(16.W)
  val negative = UInt(4.W)
  val nan = UInt(4.W)
  val inf = UInt(4.W)
  val zero = UInt(4.W)
}

class DecodedScale extends Bundle {
  val exponent = SInt(9.W) // Unbiased; mantissa is UQ1.3.
  val mantissa = UInt((Parameters.scaleFractionBits + 1).W)
  val nan = Bool()
  val zero = Bool()
}

/** Combinational decoding shared by PE and the C path.
  * No format is inferred from data bits; runtime selectors travel with each token.
  */
object Decode {
  private case class Lane(sign: Bool, exp: UInt, mant: UInt, nan: Bool, inf: Bool, zero: Bool)

  private def floating(data: UInt, expBits: Int, fracBits: Int, bias: Int,
    targetBias: Int, mantBits: Int, ieee: Boolean, finiteNan: Boolean = false): Lane = {
    val exp = data(expBits + fracBits - 1, fracBits)
    val frac = data(fracBits - 1, 0)
    val denormal = exp === 0.U
    val nan = if (ieee) exp.andR && frac.orR
      else if (finiteNan) exp.andR && frac.andR else false.B
    val inf = if (ieee) exp.andR && !frac.orR else false.B
    val effective = Mux(denormal, 1.U(expBits.W), exp)
    val rebased = effective +& (targetBias - bias).U
    val mant = Cat(!denormal, frac, 0.U((mantBits - fracBits - 1).W))
    Lane(data(expBits + fracBits), Mux(nan || inf, 1.U, rebased),
      Mux(nan || inf, 0.U, mant), nan, inf, denormal && !frac.orR)
  }

  /** Scale families are fixed by the operand format, avoiding contradictory selectors. */
  def scale(raw: UInt, format: UInt, p: PEConfig): DecodedScale = {
    val decoded = Wire(new DecodedScale)
    decoded.exponent := 0.S
    decoded.mantissa := 8.U
    decoded.nan := false.B
    decoded.zero := false.B
    if (p.hasQ || p.hasE) {
      when(!Formats.isH(format)) {
        decoded.exponent := raw.zext - 127.S
        decoded.nan := raw.andR
      }
    }
    if (p.hasE) {
      when(format === Formats.nvfp4) {
        val exp = raw(6, 3)
        val frac = raw(2, 0)
        decoded.exponent := Mux(exp === 0.U, 1.U, exp).zext - 7.S
        decoded.mantissa := Cat(exp.orR, frac)
        decoded.nan := exp.andR && frac.andR
        decoded.zero := !exp.orR && !frac.orR
      }.elsewhen(format === Formats.hif4) {
        // Source-project HiF4 contract: E6M2 bias 48, hidden one even for exp=0.
        decoded.exponent := raw(7, 2).zext - 48.S
        decoded.mantissa := Cat(1.U(1.W), raw(1, 0), 0.U(1.W))
        decoded.nan := raw.andR
      }
    }
    when(decoded.nan) {
      decoded.exponent := 0.S
      decoded.mantissa := 8.U
    }
    decoded
  }

  def scaleSlot(group: Int, format: UInt): UInt =
    Mux(format === Formats.nvfp4, group.U(2.W),
      Mux(format === Formats.mxfp4, (group / 2).U(2.W), 0.U(2.W)))

  def word(raw: UInt, format: UInt, group0: Bool, group1: Bool,
    shared: DecodedScale, p: PEConfig): DecodedWord = {
    val decoded = WireDefault(0.U.asTypeOf(new DecodedWord(p)))
    val active = Mux(Formats.isH(format), 1.U(4.W), Mux(Formats.isQ(format), 3.U(4.W), 15.U(4.W)))

    def select(code: UInt, lanes: Seq[Lane]): Unit = {
      when(format === code) {
        decoded.negative := Cat(lanes.reverse.map(_.sign))
        decoded.mantissa := Cat(lanes.reverse.map(_.mant))
        decoded.exponent := Cat(lanes.reverse.map(_.exp))
        decoded.nan := Cat(lanes.reverse.map(_.nan))
        decoded.inf := Cat(lanes.reverse.map(_.inf))
        decoded.zero := Cat(lanes.reverse.map(_.zero))
      }
    }
    if (p.hasH) {
      val fp16 = floating(raw, 5, 10, 15, 15, 12, ieee = true)
      val bf16 = floating(raw, 8, 7, 127, 127, 8, ieee = true)
      // Explicit rebased widths prevent concatenation from adding surplus exponent bits.
      select(Formats.fp16, Seq(fp16.copy(exp = fp16.exp(4, 0))))
      select(Formats.bf16, Seq(bf16.copy(exp = bf16.exp(7, 0))))
    }
    if (p.hasQ) {
      val formats = Seq((Formats.e5m2, 5, 2, 15, true, false),
        (Formats.e4m3, 4, 3, 7, false, true),
        (Formats.e3m2, 3, 2, 3, false, false),
        (Formats.e2m3, 2, 3, 1, false, false))
      for ((code, expBits, fracBits, bias, ieee, finiteNan) <- formats) {
        val lanes = (0 until 2).map { i =>
          val lane = floating(raw(8 * i + 7, 8 * i), expBits, fracBits,
            bias, 15, 4, ieee, finiteNan)
          lane.copy(exp = lane.exp.pad(5)(4, 0))
        }
        select(code, lanes)
      }
    }
    if (p.hasE) {
      val lanes = (0 until 4).map { i =>
        val nibble = raw(4 * i + 3, 4 * i)
        // 2*E2M1 magnitude: 0,1,2,3,4,6,8,12; exact UQ3.1 decoding.
        val e2m1 = MuxLookup(nibble(2, 0), 0.U(4.W))(
          Seq(0, 1, 2, 3, 4, 6, 8, 12).zipWithIndex.map { case (n, code) => code.U -> n.U(4.W) })
        val hif4 = Mux(group0, Cat(nibble(2, 0), 0.U(1.W)), Cat(0.U(1.W), nibble(2, 0)))
        Lane(nibble(3), 0.U(1.W), Mux(format === Formats.hif4, hif4, e2m1),
          false.B, false.B, !nibble(2, 0).orR)
      }
      when(Formats.isE(format)) {
        decoded.negative := Cat(lanes.reverse.map(_.sign))
        decoded.mantissa := Cat(lanes.reverse.map(_.mant))
        decoded.exponent := Mux(format === Formats.hif4, group1.asUInt, 0.U)
        decoded.zero := Cat(lanes.reverse.map(_.zero))
      }
    }
    // Combine scale and element classes once, before the product classification.
    val element_nan = decoded.nan
    val element_inf = decoded.inf
    val element_zero = decoded.zero
    val result = WireDefault(decoded)
    result.nan := (element_nan | Fill(4, shared.nan) | (element_inf & Fill(4, shared.zero))) & active
    result.inf := element_inf & ~result.nan & active
    result.zero := (element_zero | Fill(4, shared.zero)) & ~result.nan & ~result.inf & active
    result
  }

  def productSpecial(a: DecodedWord, b: DecodedWord): Special = {
    val nan = a.nan | b.nan | (a.inf & b.zero) | (b.inf & a.zero)
    val inf = (a.inf | b.inf) & ~nan
    val sign = a.negative ^ b.negative
    Special.seen(nan.orR, (inf & ~sign).orR, (inf & sign).orR)
  }

  /** FP32/FP16/BF16 C -> lossless 24-bit magnitude with physical top exponent. */
  def c(raw: UInt, format: UInt): DotResult = {
    val decoded = WireDefault(0.U.asTypeOf(new DotResult(25)))
    for ((code, expBits, fracBits, bias) <- Seq(
      (Formats.cFp32, 8, 23, 127), (Formats.cFp16, 5, 10, 15), (Formats.cBf16, 8, 7, 127))) {
      val exp = raw(expBits + fracBits - 1, fracBits)
      val frac = raw(fracBits - 1, 0)
      val sign = raw(expBits + fracBits)
      val mant = Cat(exp.orR, frac, 0.U((23 - fracBits).W))
      val special = Special.seen(exp.andR && frac.orR,
        exp.andR && !frac.orR && !sign, exp.andR && !frac.orR && sign)
      when(format === code) {
        decoded.magnitude := Mux(special.any, 0.U, mant)
        decoded.negative := sign && !special.any && mant.orR
        decoded.anchor := Mux(exp === 0.U, 1.U, exp).zext - bias.S
        decoded.special := special
      }
    }
    decoded
  }
}
