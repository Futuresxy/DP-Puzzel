package dp.utils

import chisel3._
import chisel3.util._
import dp.config._

/** H/Q-only, one global alignment followed by a four-stage natural-width tree.
  * S02 products -> S03 MAX -> S04 deltas -> S05 RTZ -> S06..S09 sum tree
  * -> S10/S11 normalization. The final magnitude is RTZ to public F=peAlignWidth.
  * This single-alignment numerical contract differs from HQE/QE's staged RTZ.
  * Valid resets, data holds on bubbles; II=1, no internal backpressure.
  */
class PEGlobalAlignNormalize(family: String, alignment: AlignmentConfig) extends Module {
  require(Set("H", "Q")(family))
  override def desiredName: String = s"PEGlobalAlignNormalize_${family}${alignment.suffix}"
  private val lanesPerGroup = if (family == "H") 4 else 8
  private val laneCount = lanesPerGroup * 4
  private val magnitudeWidth = if (family == "H") 22 else 8
  private val alignWidth = alignment.peAlignWidth
  private val sumWidth = alignWidth + log2Ceil(laneCount)
  private val resultWidth = alignment.peResultWidth
  private val shiftWidth = log2Ceil(alignWidth + 1)
  private val zeroAnchor = (-1024).S(11.W)
  require(alignWidth > magnitudeWidth && sumWidth >= resultWidth)
  val io = IO(new Bundle {
    val in_products = Flipped(Vec(4, Valid(new RawProducts(lanesPerGroup, magnitudeWidth))))
    val in_anchor_offset = Input(SInt(11.W))
    val out_data = Valid(new PEDotResult(resultWidth))
  })
  val input_valid = io.in_products.head.valid
  io.in_products.foreach(source => assert(source.valid === input_valid))
  val raw_magnitudes = VecInit(io.in_products.flatMap(_.bits.magnitude))
  val raw_negatives = VecInit(io.in_products.flatMap(_.bits.negative))
  val raw_zeros = VecInit(io.in_products.flatMap(_.bits.is_zero))
  val raw_anchors = VecInit(io.in_products.flatMap(_.bits.top_anchor).zipWithIndex.map {
    case (anchor, index) => Mux(raw_zeros(index), zeroAnchor, anchor)
  })
  val (max_anchor, _) = MaxLaneAlign.maximum(raw_anchors.toSeq)
  val selected_anchor = Mux(raw_zeros.asUInt.andR, 0.S(11.W), max_anchor)
  val special = SpecialValueFlags.mergeAdd(io.in_products.map(_.bits.special))
  val s03_valid_q = RegNext(input_valid, false.B)
  val s03_magnitudes_q = RegEnable(raw_magnitudes, input_valid)
  val s03_negatives_q = RegEnable(raw_negatives, input_valid)
  val s03_zeros_q = RegEnable(raw_zeros, input_valid)
  val s03_anchors_q = RegEnable(raw_anchors, input_valid)
  val s03_base_anchor_q = RegEnable(selected_anchor, input_valid)
  val s03_top_anchor_q = RegEnable(selected_anchor + io.in_anchor_offset, input_valid)
  val s03_special_q = RegEnable(special, input_valid)

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
