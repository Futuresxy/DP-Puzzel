package dp.pe.q

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** 32-lane Q PE: complete decode/product/alignment/accumulation pipeline here.
  * No SubPE/PEGroup hierarchy. S01 input, S02 products, S03 MAX, S04 deltas,
  * S05 RTZ, S06-S09 natural-width tree, S10-S11 generic normalization.
  * II=1, Valid-only; cfg stable through drain, valid resets, payload holds on bubbles.
  * Public F=peAlignWidth; final low-bit RTZ differs from shared-family staged RTZ.
  */
class PE_Q(alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_Q_g4"), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val laneCount = 32
  private val magnitudeWidth = 8
  private val alignWidth = alignment.peAlignWidth
  private val sumWidth = alignWidth + log2Ceil(laneCount)
  private val resultWidth = alignment.peResultWidth
  private val shiftWidth = log2Ceil(alignWidth + 1)
  private val zeroAnchor = (-1024).S(11.W)
  require(alignWidth > magnitudeWidth && sumWidth >= resultWidth)

  // S00: cfg owns element/scale types; nested input tags are not controls.
  // cfg remains stable until the batch has drained. There is no backpressure.
  private val input_legal = Precision.q.supportsDataType(io.in_cfg.data_type) &&
    Precision.q.supportsDataType(io.in_cfg.b_data_type) &&
    FormatCompat.legalABPair(io.in_cfg.data_type, io.in_cfg.b_data_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.data_type, io.in_cfg.sf_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
  when(io.in_data.valid) { assert(input_legal, "PE requires legal supported A/B and scale formats") }
  private val input_fire = io.in_data.valid && input_legal

  // S01: retain the original compact input register. Decode and multiply
  // occur together before S02, so flattening introduces no new register boundary.
  val s01_valid_q = RegNext(input_fire, false.B)
  val s01_words_q = RegEnable(VecInit(io.in_data.bits.a.data, io.in_data.bits.b.data), input_fire)
  val s01_types_q = RegEnable(VecInit(io.in_cfg.data_type, io.in_cfg.b_data_type), input_fire)
  val scale_nan = VecInit(io.in_data.bits.a.sf.sf_data(0).andR, io.in_data.bits.b.sf.sf_data(0).andR)
  val s01_scale_nan_q = RegEnable(scale_nan, input_fire)
  val a_scale_exp = Mux(scale_nan(0), 127.U(8.W), io.in_data.bits.a.sf.sf_data(0))
  val b_scale_exp = Mux(scale_nan(1), 127.U(8.W), io.in_data.bits.b.sf.sf_data(0))
  val s01_scale_exp_q = RegEnable((a_scale_exp +& b_scale_exp).zext - 254.S, input_fire)

  // Decode each byte independently. FP6 uses its low six bits; bits7:6 are ignored.
  // All four formats become E5(bias15) plus UQ1.3 (hidden bit included):
  // E5M2 -> {hidden,m2,0}; E4M3 -> {hidden,m3}; E3M2/E2M3 rebase by +12/+14.
  val decoded_mant = Wire(Vec(2, Vec(laneCount, UInt(4.W))))
  val decoded_exp = Wire(Vec(2, Vec(laneCount, UInt(5.W))))
  val decoded_sign = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_nan = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_inf = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_zero = Wire(Vec(2, Vec(laneCount, Bool())))
  for (side <- 0 until 2; lane <- 0 until laneCount) {
    val low = (lane % 2) * 8
    val byte = s01_words_q(side)(lane / 2)(low + 7, low)
    val exponent = WireDefault(0.U(5.W))
    val mantissa = WireDefault(0.U(4.W))
    val sign = WireDefault(false.B)
    val element_nan = WireDefault(false.B)
    val element_inf = WireDefault(false.B)
    val element_zero = WireDefault(false.B)
    switch(s01_types_q(side)) {
      is(DataType.e5_m2) {
        val exp = byte(6, 2)
        val exp_zero = exp === 0.U
        val special = exp.andR
        exponent := Mux(exp_zero || special, 1.U(5.W), exp)
        mantissa := Mux(special, 0.U(4.W), Cat(!exp_zero, byte(1, 0), 0.U(1.W)))
        sign := byte(7)
        element_nan := special && byte(1, 0).orR
        element_inf := special && !byte(1, 0).orR
        element_zero := !byte(6, 0).orR
      }
      is(DataType.e4_m3) {
        val exp = byte(6, 3)
        val exp_zero = exp === 0.U
        val nan = byte(6, 0).andR
        // exp15/mant0..6 remain finite; only the all-ones magnitude is NaN.
        exponent := Mux(nan, 1.U(5.W), Mux(exp_zero, 9.U(5.W), exp +& 8.U))
        mantissa := Mux(nan, 0.U(4.W), Cat(!exp_zero, byte(2, 0)))
        sign := byte(7)
        element_nan := nan
        element_zero := !byte(6, 0).orR
      }
      is(DataType.e3_m2) {
        val exp = byte(4, 2)
        val exp_zero = exp === 0.U
        exponent := Mux(exp_zero, 13.U(5.W), exp +& 12.U)
        mantissa := Cat(!exp_zero, byte(1, 0), 0.U(1.W))
        sign := byte(5)
        element_zero := !byte(4, 0).orR
      }
      is(DataType.e2_m3) {
        val exp = byte(4, 3)
        val exp_zero = exp === 0.U
        exponent := Mux(exp_zero, 15.U(5.W), exp +& 14.U)
        mantissa := Cat(!exp_zero, byte(2, 0))
        sign := byte(5)
        element_zero := !byte(4, 0).orR
      }
    }
    decoded_mant(side)(lane) := mantissa
    decoded_exp(side)(lane) := exponent
    decoded_sign(side)(lane) := sign
    operand_nan(side)(lane) := element_nan || s01_scale_nan_q(side)
    operand_inf(side)(lane) := element_inf && !operand_nan(side)(lane)
    operand_zero(side)(lane) := element_zero && !operand_nan(side)(lane) && !operand_inf(side)(lane)
  }

  // S02: 32 independent 4x4 -> UQ2.6 W8 products. No word/PG-local MAX or sum.
  // A product's magnitude bit7 has exponent expA+expB-30+1 before block scaling.
  val magnitudes = Wire(Vec(laneCount, UInt(magnitudeWidth.W)))
  val negatives = Wire(Vec(laneCount, Bool()))
  val zeros = Wire(Vec(laneCount, Bool()))
  val anchors = Wire(Vec(laneCount, SInt(11.W)))
  val product_nan = Wire(Vec(laneCount, Bool()))
  val product_pos_inf = Wire(Vec(laneCount, Bool()))
  val product_neg_inf = Wire(Vec(laneCount, Bool()))
  for (lane <- 0 until laneCount) {
    val product = decoded_mant(0)(lane) * decoded_mant(1)(lane)
    val exponent_sum = decoded_exp(0)(lane) +& decoded_exp(1)(lane)
    val negative = decoded_sign(0)(lane) ^ decoded_sign(1)(lane)
    magnitudes(lane) := product
    negatives(lane) := negative && product.orR
    zeros(lane) := !product.orR
    anchors(lane) := Mux(product.orR, exponent_sum.zext - 29.S, zeroAnchor)
    val invalid = operand_nan(0)(lane) || operand_nan(1)(lane) ||
      (operand_inf(0)(lane) && operand_zero(1)(lane)) ||
      (operand_zero(0)(lane) && operand_inf(1)(lane))
    val infinite = (operand_inf(0)(lane) || operand_inf(1)(lane)) && !invalid
    product_nan(lane) := invalid
    product_pos_inf(lane) := infinite && !negative
    product_neg_inf(lane) := infinite && negative
  }
  val product_special = SpecialValueFlags.fromSeen(
    product_nan.asUInt.orR, product_pos_inf.asUInt.orR, product_neg_inf.asUInt.orR)
  val s02_valid_q = RegNext(s01_valid_q, false.B)
  val s02_magnitudes_q = RegEnable(magnitudes, s01_valid_q)
  val s02_negatives_q = RegEnable(negatives, s01_valid_q)
  val s02_zeros_q = RegEnable(zeros, s01_valid_q)
  val s02_anchors_q = RegEnable(anchors, s01_valid_q)
  val s02_special_q = RegEnable(product_special, s01_valid_q)
  val s02_scale_exp_q = RegEnable(s01_scale_exp_q, s01_valid_q)
  // One E8M0 scale per operand covers all 32 lanes. It changes the global
  // anchor after MAX, not lane differences; E8M0 needs no scale-tail multiplier.
  val anchor_offset = s02_scale_exp_q

  // S03: one balanced MAX across the entire K dimension; zeros cannot win.
  val raw_anchors = VecInit(s02_anchors_q.zipWithIndex.map {
    case (anchor, index) => Mux(s02_zeros_q(index), zeroAnchor, anchor)
  })
  val (max_anchor, _) = MaxLaneAlign.maximum(raw_anchors.toSeq)
  val selected_anchor = Mux(s02_zeros_q.asUInt.andR, 0.S(11.W), max_anchor)
  val s03_valid_q = RegNext(s02_valid_q, false.B)
  val s03_magnitudes_q = RegEnable(s02_magnitudes_q, s02_valid_q)
  val s03_negatives_q = RegEnable(s02_negatives_q, s02_valid_q)
  val s03_zeros_q = RegEnable(s02_zeros_q, s02_valid_q)
  val s03_anchors_q = RegEnable(raw_anchors, s02_valid_q)
  val s03_base_anchor_q = RegEnable(selected_anchor, s02_valid_q)
  val s03_top_anchor_q = RegEnable(selected_anchor + anchor_offset, s02_valid_q)
  val s03_special_q = RegEnable(s02_special_q, s02_valid_q)

  // S04: per-product exponent differences, saturated at the alignment window.
  val shifts = VecInit((0 until laneCount).map { index =>
    val delta = (s03_base_anchor_q.pad(13) - s03_anchors_q(index).pad(13)).asUInt
    Mux(s03_zeros_q(index), 0.U(shiftWidth.W),
      Mux(delta >= alignWidth.U, alignWidth.U(shiftWidth.W), delta(shiftWidth - 1, 0)))
  })
  val s04_valid_q = RegNext(s03_valid_q, false.B)
  val s04_shifts_q = RegEnable(shifts, s03_valid_q)
  val s04_magnitudes_q = RegEnable(s03_magnitudes_q, s03_valid_q)
  val s04_negatives_q = RegEnable(s03_negatives_q, s03_valid_q)
  val s04_top_anchor_q = RegEnable(s03_top_anchor_q, s03_valid_q)
  val s04_special_q = RegEnable(s03_special_q, s03_valid_q)
  // S05: unsigned right shift followed by sign application implements RTZ.
  // Independent lane shifters avoid a 16/32-lane permutation crossbar.
  val aligned = VecInit((0 until laneCount).map { index =>
    val placed = Cat(s04_magnitudes_q(index), 0.U((alignWidth - 1 - magnitudeWidth).W))
    val magnitude = (placed >> s04_shifts_q(index)).zext
    Mux(s04_negatives_q(index), -magnitude, magnitude)
  })
  val s05_valid_q = RegNext(s04_valid_q, false.B)
  val s05_terms_q = RegEnable(aligned, s04_valid_q)
  val s05_top_anchor_q = RegEnable(s04_top_anchor_q, s04_valid_q)
  val s05_special_q = RegEnable(s04_special_q, s04_valid_q)

  // S06-S09: natural-width accumulation; anchor/special/valid advance together.
  // Three pair levels, then one/two final levels. Every adder uses +&.
  var terms: Seq[SInt] = s05_terms_q.toSeq
  var valid: Bool = s05_valid_q
  var anchor: SInt = s05_top_anchor_q
  var flags: SpecialValueFlags = s05_special_q
  for (stage <- 6 to 9) {
    val nextTerms = if (stage < 9) terms.grouped(2).map(pair => pair.head +& pair(1)).toSeq
      else Seq(VecInit(terms).reduceTree(_ +& _))
    val data_q = RegEnable(VecInit(nextTerms), valid).suggestName(s"s${stage}_sum_q")
    val anchor_q = RegEnable(anchor, valid).suggestName(s"s${stage}_top_anchor_q")
    val special_q = RegEnable(flags, valid).suggestName(s"s${stage}_special_q")
    val valid_q = RegNext(valid, false.B).suggestName(s"s${stage}_valid_q")
    terms = data_q.toSeq
    anchor = anchor_q
    flags = special_q
    valid = valid_q
  }
  require(terms.size == 1 && terms.head.getWidth == sumWidth, "Natural tree carry growth mismatch")
  // S10-S11: generic normalization, then the explicit public-window RTZ boundary.
  val normalize = Module(new PENormalizeExact(PENormalizeExactConfig(sumWidth, 11)))
  normalize.io.in_data.valid := valid
  normalize.io.in_data.bits.result := terms.head
  normalize.io.in_data.bits.raw_top_anchor := anchor + log2Ceil(laneCount).S
  normalize.io.in_data.bits.special := flags
  private val dropBits = sumWidth - resultWidth
  io.out_data.valid := normalize.io.out_data.valid
  io.out_data.bits.magnitude := normalize.io.out_data.bits.magnitude(sumWidth - 2, dropBits)
  io.out_data.bits.negative := normalize.io.out_data.bits.negative
  io.out_data.bits.top_anchor := normalize.io.out_data.bits.normalized_top_anchor
  io.out_data.bits.is_zero := normalize.io.out_data.bits.is_zero
  io.out_data.bits.special := normalize.io.out_data.bits.special
}
