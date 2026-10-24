package dp.pe.h

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** 16-lane H PE: complete decode/product/alignment/accumulation pipeline here.
  * No SubPE/PEGroup hierarchy. S01 input, S02 products, S03 MAX, S04 deltas,
  * S05 RTZ, S06-S09 natural-width tree, S10-S11 generic normalization.
  * II=1, Valid-only; cfg stable through drain, valid resets, payload holds on bubbles.
  * Public F=peAlignWidth; final low-bit RTZ differs from shared-family staged RTZ.
  */
class PE_H(alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_H_g4"), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val laneCount = 16
  private val magnitudeWidth = 22
  private val alignWidth = alignment.peAlignWidth
  private val sumWidth = alignWidth + log2Ceil(laneCount)
  private val resultWidth = alignment.peResultWidth
  private val shiftWidth = log2Ceil(alignWidth + 1)
  private val zeroAnchor = (-1024).S(11.W)
  require(alignWidth > magnitudeWidth && sumWidth >= resultWidth)

  // S00: cfg owns element/scale types; nested input tags are not controls.
  // cfg remains stable until the batch has drained. There is no backpressure.
  private val input_legal = Precision.h.supportsDataType(io.in_cfg.data_type) &&
    Precision.h.supportsDataType(io.in_cfg.b_data_type) &&
    FormatCompat.legalABPair(io.in_cfg.data_type, io.in_cfg.b_data_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.data_type, io.in_cfg.sf_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
  when(io.in_data.valid) { assert(input_legal, "PE requires legal supported A/B and scale formats") }
  private val input_fire = io.in_data.valid && input_legal

  // S01: decode FP16/BF16 directly into UQ1.10, retaining biased exponents.
  // BF16 appends three exact low zeros. Subnormals use hidden=0 and exponent=1.
  // NaN/Inf have a zero numerical placeholder and an independent special sideband.
  private val is_bf16 = io.in_cfg.data_type === DataType.bf16
  val decoded_mant = Wire(Vec(2, Vec(laneCount, UInt(11.W))))
  val decoded_exp = Wire(Vec(2, Vec(laneCount, UInt(8.W))))
  val decoded_sign = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_nan = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_inf = Wire(Vec(2, Vec(laneCount, Bool())))
  val operand_zero = Wire(Vec(2, Vec(laneCount, Bool())))
  for ((operand, side) <- Seq(io.in_data.bits.a, io.in_data.bits.b).zipWithIndex;
       lane <- 0 until laneCount) {
    val word = operand.data(lane)
    val exponent = Mux(is_bf16, word(14, 7), word(14, 10).pad(8))
    val fraction_nonzero = Mux(is_bf16, word(6, 0).orR, word(9, 0).orR)
    val exponent_zero = exponent === 0.U
    val exponent_special = Mux(is_bf16, word(14, 7).andR, word(14, 10).andR)
    val mantissa = Mux(is_bf16,
      Cat(!exponent_zero, word(6, 0), 0.U(3.W)), Cat(!exponent_zero, word(9, 0)))
    decoded_mant(side)(lane) := Mux(exponent_special, 0.U(11.W), mantissa)
    decoded_exp(side)(lane) := Mux(exponent_zero || exponent_special, 1.U(8.W), exponent)
    decoded_sign(side)(lane) := word(15)
    operand_nan(side)(lane) := exponent_special && fraction_nonzero
    operand_inf(side)(lane) := exponent_special && !fraction_nonzero
    operand_zero(side)(lane) := exponent_zero && !fraction_nonzero
  }
  val product_nan = Wire(Vec(laneCount, Bool()))
  val product_pos_inf = Wire(Vec(laneCount, Bool()))
  val product_neg_inf = Wire(Vec(laneCount, Bool()))
  for (lane <- 0 until laneCount) {
    val invalid = operand_nan(0)(lane) || operand_nan(1)(lane) ||
      (operand_inf(0)(lane) && operand_zero(1)(lane)) ||
      (operand_zero(0)(lane) && operand_inf(1)(lane))
    val infinite = (operand_inf(0)(lane) || operand_inf(1)(lane)) && !invalid
    val negative = decoded_sign(0)(lane) ^ decoded_sign(1)(lane)
    product_nan(lane) := invalid
    product_pos_inf(lane) := infinite && !negative
    product_neg_inf(lane) := infinite && negative
  }
  val input_special = SpecialValueFlags.fromSeen(
    product_nan.asUInt.orR, product_pos_inf.asUInt.orR, product_neg_inf.asUInt.orR)
  val s01_valid_q = RegNext(input_fire, false.B)
  val s01_mant_q = RegEnable(decoded_mant, input_fire)
  val s01_exp_q = RegEnable(decoded_exp, input_fire)
  val s01_sign_q = RegEnable(decoded_sign, input_fire)
  val s01_bf16_q = RegEnable(is_bf16, input_fire)
  val s01_special_q = RegEnable(input_special, input_fire)

  // S02: all 16 independent 11x11 products are UQ2.20, with no local sum.
  // top_anchor describes physical magnitude bit21: expA+expB-2*bias+1.
  val magnitudes = Wire(Vec(laneCount, UInt(magnitudeWidth.W)))
  val negatives = Wire(Vec(laneCount, Bool()))
  val zeros = Wire(Vec(laneCount, Bool()))
  val anchors = Wire(Vec(laneCount, SInt(11.W)))
  for (lane <- 0 until laneCount) {
    val product = s01_mant_q(0)(lane) * s01_mant_q(1)(lane)
    val exponent_sum = s01_exp_q(0)(lane) +& s01_exp_q(1)(lane)
    val top_anchor = exponent_sum.zext - Mux(s01_bf16_q, 254.S(11.W), 30.S(11.W)) + 1.S
    magnitudes(lane) := product
    negatives(lane) := (s01_sign_q(0)(lane) ^ s01_sign_q(1)(lane)) && product.orR
    zeros(lane) := !product.orR
    anchors(lane) := Mux(product.orR, top_anchor, zeroAnchor)
  }
  val s02_valid_q = RegNext(s01_valid_q, false.B)
  val s02_magnitudes_q = RegEnable(magnitudes, s01_valid_q)
  val s02_negatives_q = RegEnable(negatives, s01_valid_q)
  val s02_zeros_q = RegEnable(zeros, s01_valid_q)
  val s02_anchors_q = RegEnable(anchors, s01_valid_q)
  val s02_special_q = RegEnable(s01_special_q, s01_valid_q)
  // High precision uses a virtual unit block scale; no scale arithmetic exists.
  val anchor_offset = 0.S(11.W)

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
