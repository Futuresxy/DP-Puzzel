package dp.pe

import chisel3._
import chisel3.util._
import dp.config._
import dp.common._

/** Scaled A dot B only. Fixed 11-cycle latency, one token/cycle, no backpressure.
  * sub_H* and group_H* are inline arithmetic regions, never Module instances.
  * All format controls are sampled per token; bubbles hold data registers.
  */
class PE(val p: PEConfig) extends Module {
  override def desiredName: String = s"PE_${p.tag}${p.widthSuffix}"
  val io = IO(new Bundle {
    val in = Flipped(Valid(new PEInput(p)))
    val out = Valid(new DotResult(p.resultWidth))
  })
  private val legal = Formats.legal(p, io.in.bits.a_format, io.in.bits.b_format)
  when(io.in.valid) { assert(legal, "PE received an unsupported format pair") }
  private val valid = (1 to Parameters.peLatency).scanLeft(io.in.valid && legal) { (previous, stage) =>
    RegNext(previous, false.B).suggestName(s"s${stage}_valid_q")
  }
  private val s1_format_q = RegEnable(Formats.product(io.in.bits.a_format, io.in.bits.b_format), valid(0))
  private val s6_format_q = Arithmetic.delay(s1_format_q, valid(1), 5, "format_s6")

  /** Inline packed-word products. Exponent at S2; signed fixed-point data at S4. */
  private def wordProduct(a: DecodedWord, b: DecodedWord, index: Int): (UInt, SInt) = {
    val prefix = s"${p.subTag}_${index}"
    val is_q = Formats.isQ(s1_format_q)
    val is_bf16 = s1_format_q === Formats.bf16
    val is_fp16 = s1_format_q === Formats.fp16
    val is_h = Formats.isH(s1_format_q)
    def nibble(value: UInt, lane: Int): UInt = value(4 * lane + 3, 4 * lane)

    // H reuses 4x4, 4x8, 8x4, 8x8 partial products. Q uses the first two;
    // E uses all four with zero-extended 4-bit operands. Disabled families vanish.
    val sizes = if (p.hasH) Seq((4, 4), (4, 8), (8, 4), (8, 8))
      else Seq.fill(if (p.hasE) 4 else 2)((4, 4))
    val products_q = sizes.zipWithIndex.map { case ((aWidth, bWidth), lane) =>
      val mul_a = WireDefault(0.U(aWidth.W))
      val mul_b = WireDefault(0.U(bWidth.W))
      if (p.hasE) {
        when(Formats.isE(s1_format_q)) {
          mul_a := nibble(a.mantissa, lane)
          mul_b := nibble(b.mantissa, lane)
        }
      }
      if (p.hasQ && lane < 2) {
        when(is_q) {
          mul_a := nibble(a.mantissa, lane)
          mul_b := nibble(b.mantissa, lane)
        }
      }
      if (p.hasH) {
        when(is_fp16) {
          mul_a := (if (lane < 2) a.mantissa(3, 0) else a.mantissa(11, 4))
          mul_b := (if (lane % 2 == 0) b.mantissa(3, 0) else b.mantissa(11, 4))
        }
        if (lane == 3) {
          when(is_bf16) { mul_a := a.mantissa(7, 0); mul_b := b.mantissa(7, 0) }
        }
      }
      RegEnable(mul_a * mul_b, valid(1)).suggestName(s"${prefix}_s2_product_${lane}_q")
    }
    val s2_sign_q = RegEnable(a.negative ^ b.negative, valid(1))
    val s2_format_q = RegEnable(s1_format_q, valid(1))
    val anchor = WireDefault(0.U(9.W))
    val q_hi_max = WireDefault(false.B)
    val q_delta = WireDefault(0.U(6.W))
    if (p.hasH) {
      val exp_a = Mux(is_bf16, a.exponent(7, 0), a.exponent(4, 0))
      val exp_b = Mux(is_bf16, b.exponent(7, 0), b.exponent(4, 0))
      when(is_h) { anchor := Mux(a.mantissa.orR && b.mantissa.orR, exp_a +& exp_b, 0.U) }
    }
    if (p.hasQ) {
      val exponents = (0 until 2).map { lane =>
        val sum = a.exponent(5 * lane + 4, 5 * lane) +& b.exponent(5 * lane + 4, 5 * lane)
        Mux(nibble(a.mantissa, lane).orR && nibble(b.mantissa, lane).orR, sum, 0.U)
      }
      q_hi_max := exponents(1) > exponents(0)
      q_delta := Mux(q_hi_max, exponents(1) - exponents(0), exponents(0) - exponents(1))
      when(is_q) { anchor := Mux(q_hi_max, exponents(1), exponents(0)) }
    }
    if (p.hasE) {
      when(Formats.isE(s1_format_q)) { anchor := a.exponent(0) +& b.exponent(0) }
    }
    val s2_anchor_q = RegEnable(anchor, valid(1)).suggestName(s"${prefix}_s2_anchor_q")
    val s2_hi_max_q = RegEnable(q_hi_max, valid(1))
    val s2_delta_q = RegEnable(q_delta, valid(1))

    // S3 stores operands of the shared final adder; Q's maximum needs no shifter.
    val low_a = WireDefault(0.S((p.wordWidth - 1).W))
    val low_b = WireDefault(0.S((p.wordWidth - 1).W))
    if (p.hasE) {
      val signed = products_q.zipWithIndex.map { case (product, lane) =>
        Arithmetic.signed(product(7, 0), s2_sign_q(lane))
      }
      low_a := Arithmetic.append(signed(0) +& signed(1), p.wordWidth - 11)
      low_b := Arithmetic.append(signed(2) +& signed(3), p.wordWidth - 11)
    }
    if (p.hasQ) {
      val maximum = Mux(s2_hi_max_q, products_q(1)(7, 0), products_q(0)(7, 0))
      val minimum = Mux(s2_hi_max_q, products_q(0)(7, 0), products_q(1)(7, 0))
      val max_sign = Mux(s2_hi_max_q, s2_sign_q(1), s2_sign_q(0))
      val min_sign = Mux(s2_hi_max_q, s2_sign_q(0), s2_sign_q(1))
      // W28 = sign + 2 integer + 25 fractional positions (8 product + 19 zeros).
      val aligned_min = Cat(minimum, 0.U(Parameters.qGuardBits.W)) >> s2_delta_q
      when(Formats.isQ(s2_format_q)) {
        low_a := Arithmetic.append(Arithmetic.signed(maximum, max_sign), Parameters.qGuardBits)
        low_b := Arithmetic.signed(aligned_min, min_sign)
      }
    }
    val s3_low_a_q = RegEnable(low_a, valid(2))
    val s3_low_b_q = RegEnable(low_b, valid(2))
    val result = Wire(SInt(p.wordWidth.W))
    result := s3_low_a_q +& s3_low_b_q
    if (p.hasH) {
      val s3_base_q = RegEnable(Cat(products_q(3), products_q(0)), valid(2))
      val s3_cross_q = RegEnable(products_q(1) +& products_q(2), valid(2))
      val s3_bf16_q = RegEnable(Cat(products_q(3), 0.U(6.W)), valid(2))
      val s3_sign_q = RegEnable(s2_sign_q(0), valid(2))
      val s3_format_q = RegEnable(s2_format_q, valid(2))
      val reconstructed = s3_base_q +& (s3_cross_q << 4)
      val magnitude = Mux(s3_format_q === Formats.bf16, s3_bf16_q, reconstructed(23, 2))
      when(Formats.isH(s3_format_q)) {
        // FP16 decode appended one zero per operand; removing those two bits is exact.
        result := Arithmetic.append(Arithmetic.signed(magnitude, s3_sign_q), p.wordWidth - Parameters.halfProductWidth)
      }
    }
    val s4_result_q = RegEnable(result, valid(3)).suggestName(s"${prefix}_s4_result_q")
    (s2_anchor_q, s4_result_q)
  }

  // Each inline group covers four packed words, matching the smallest scale block.
  val groups = (0 until p.groups).map { group =>
    val prefix = s"${p.groupTag}_${group}"
    def operand(source: Operand, format: UInt): (Seq[DecodedWord], DecodedScale) = {
      val slot = Decode.scaleSlot(group, format)
      val raw_scale = source.scale(if (p.groups == 2) slot(0) else slot)
      when(valid(0) && format === Formats.nvfp4) {
        assert(!raw_scale(7), "NVFP4 block scale must be nonnegative E4M3")
      }
      val scale = Decode.scale(raw_scale, format, p)
      val words = (0 until 4).map { local =>
        val index = group * 4 + local
        val decoded = Decode.word(source.data(index), format, source.group0(index),
          source.group1(index / 2), scale, p)
        RegEnable(decoded, valid(0)).suggestName(s"${prefix}_word_${local}_decode_q")
      }
      (words, RegEnable(scale, valid(0)))
    }
    val (a, a_scale) = operand(io.in.bits.a, io.in.bits.a_format)
    val (b, b_scale) = operand(io.in.bits.b, io.in.bits.b_format)
    val words = (0 until 4).map(i => wordProduct(a(i), b(i), group * 4 + i))
    val s2_scale_exp_q = RegEnable(a_scale.exponent +& b_scale.exponent, valid(1))
    val s2_scale_mant_q = RegEnable(a_scale.mantissa * b_scale.mantissa, valid(1))
    val s2_special_q = RegEnable(Special.merge(a.zip(b).map { case (a, b) => Decode.productSpecial(a, b) }), valid(1))

    val anchors = words.map(_._1.zext)
    val (max_anchor, max_index) = Arithmetic.maximum(anchors)
    val s3_anchor_q = RegEnable(max_anchor, valid(2))
    val s3_index_q = RegEnable(max_index, valid(2))
    val s3_anchors_q = RegEnable(VecInit(anchors), valid(2))
    val s4_anchor_q = Arithmetic.delay(s3_anchor_q, valid(3), 1, s"${prefix}_anchor_s4")

    val (local_values, correction, sumWidth) = if (p.onlyE) {
      // Adjacent words share HiF4 group1. Pair before alignment: one 2-bit shifter.
      val s4_shift_q = RegEnable(Arithmetic.delta(s3_anchor_q, Mux(s3_index_q < 2.U,
        s3_anchors_q(2), s3_anchors_q(0)), 3), valid(3))
      val s4_high_q = RegEnable(s3_index_q >= 2.U, valid(3))
      val pair0 = words(0)._2 +& words(1)._2
      val pair1 = words(2)._2 +& words(3)._2
      val maximum = Mux(s4_high_q, pair1, pair0)
      val minimum = Mux(s4_high_q, pair0, pair1)
      val aligned = Arithmetic.append(minimum, 2) >> s4_shift_q
      when(valid(4)) { assert(s4_shift_q <= 2.U, "HiF4 pair exponent delta exceeds two") }
      (VecInit(Arithmetic.append(maximum, 2), aligned), 0.U(1.W), 15)
    } else {
      val alignedWidth = p.wordWidth + 2
      val s4_shifts_q = RegEnable(VecInit(s3_anchors_q.map(Arithmetic.delta(s3_anchor_q, _, alignedWidth))), valid(3))
      val s4_index_q = RegEnable(s3_index_q, valid(3))
      val (floors, corrections) = Arithmetic.align(words.map(w => Arithmetic.append(w._2, 2)),
        s4_shifts_q.toSeq, s4_index_q)
      (floors, corrections, p.groupWidth)
    }
    val s5_values_q = RegEnable(local_values, valid(4))
    val s5_correction_q = RegEnable(correction, valid(4))
    val s6_sum_q = RegEnable(Arithmetic.sum(s5_values_q.toSeq :+ s5_correction_q.zext, sumWidth), valid(5))
    val s6_anchor_q = Arithmetic.delay(s4_anchor_q, valid(4), 2, s"${prefix}_anchor_s6")
    val s6_scale_exp_q = Arithmetic.delay(s2_scale_exp_q, valid(2), 4, s"${prefix}_scale_exp_s6")
    val s6_scale_mant_q = Arithmetic.delay(s2_scale_mant_q, valid(2), 4, s"${prefix}_scale_mant_s6")
    val s7_special_q = Arithmetic.delay(s2_special_q, valid(2), 5, s"${prefix}_special_s7")

    val result = Wire(SInt(p.groupWidth.W))
    val top_offset = Wire(SInt(11.W))
    if (p.onlyE) {
      val product = s6_sum_q * s6_scale_mant_q.zext // W15 * W9 -> W24.
      when(valid(6)) { assert(!product.asUInt(1, 0).orR, "E-only scale crop must remove only structural zeros") }
      result := product.asUInt(23, 2).asSInt
      top_offset := Mux(s6_format_q === Formats.hif4, 10.S, 12.S)
    } else {
      result := s6_sum_q
      // Full/Low fractional scale multiply reads only the structurally nonzero prefix.
      if (p.hasE) {
        val use_mantissa = s6_format_q === Formats.nvfp4 || s6_format_q === Formats.hif4
        val compact = s6_sum_q.asUInt(p.groupWidth - 1, 18).asSInt
        val product = compact * Mux(use_mantissa, s6_scale_mant_q, 0.U(8.W)).zext
        when(use_mantissa) { result := Arithmetic.append(product, p.groupWidth - product.getWidth) }
        when(valid(6) && use_mantissa) {
          assert(!s6_sum_q.asUInt(17, 0).orR, "Scale multiplier may discard only structural FP4 zeros")
        }
      }
      top_offset := MuxLookup(s6_format_q, 0.S(11.W))(Seq(
        Formats.fp16 -> (-27).S(11.W), Formats.bf16 -> (-251).S(11.W),
        Formats.e5m2 -> (-26).S(11.W), Formats.mxfp4 -> 9.S(11.W),
        Formats.nvfp4 -> 12.S(11.W), Formats.hif4 -> 10.S(11.W)))
    }
    val physical_anchor = s6_anchor_q.pad(11) + s6_scale_exp_q.pad(11) + top_offset
    val s7_result_q = RegEnable(result, valid(6)).suggestName(s"${prefix}_s7_result_q")
    val s7_anchor_q = RegEnable(physical_anchor, valid(6)).suggestName(s"${prefix}_s7_anchor_q")
    (s7_result_q, s7_anchor_q, s7_special_q)
  }

  // S8-S11: cross-scale reduction and exact normalization. Zero groups cannot win MAX.
  private val zero_anchor = (-1024).S(11.W)
  private val group_anchors = groups.map { case (value, anchor, _) => Mux(value === 0.S, zero_anchor, anchor) }
  private val (maximum, winner) = Arithmetic.maximum(group_anchors)
  private val top = Mux(maximum === zero_anchor, 0.S(11.W), maximum)
  private val shifts = group_anchors.map(Arithmetic.delta(top, _, p.alignWidth))
  private val placed = groups.map(g => Arithmetic.append(g._1, p.alignWidth - p.groupWidth))
  private val (aligned, correction) = Arithmetic.align(placed, shifts, winner)
  private val s8_data_q = RegEnable(aligned, valid(7))
  private val s8_correction_q = RegEnable(correction, valid(7))
  private val sumWidth = p.alignWidth + log2Ceil(p.groups)
  private val s8_anchor_q = RegEnable(top + log2Ceil(p.groups).S, valid(7))
  private val s9_sum_q = RegEnable(Arithmetic.sum(s8_data_q.toSeq :+ s8_correction_q.zext, sumWidth), valid(8))
  private val s9_anchor_q = RegEnable(s8_anchor_q, valid(8))
  private val s9_special_q = Arithmetic.delay(Special.merge(groups.map(_._3)), valid(7), 2, "special_s9")
  private val normalized = Normalize.exact(s9_sum_q, s9_anchor_q, s9_special_q, valid(9), p.resultWidth)
  io.out.valid := valid(11)
  io.out.bits := normalized
}
