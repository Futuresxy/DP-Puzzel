package dp.utils

import dp.config._
import dp.utils._
import dp.utils.{CarrySave, MaxLaneAlign}
import chisel3._
import chisel3.util._

/** Two- or four-way forward reduction with one global schedule and output coordinate. */
class PEAlignNormalize(
  groupDataWidth: Int,
  groupCount: Int = PEContract.groupCount,
  alignment: AlignmentConfig = AlignmentConfig()
) extends Module {
  require(groupCount == 2 || groupCount == PEContract.groupCount)
  private val alignWidth = alignment.peAlignWidth
  private val anchorWidth = PEContract.anchorWidth
  private val outDataWidth = PEContract.publicDataWidth(alignWidth)
  private val carryBits = log2Ceil(groupCount)
  private val sumDataWidth = alignWidth + carryBits
  private val placementZeros = alignWidth - groupDataWidth
  private val shiftWidth = log2Ceil(alignWidth + 1)
  private val calcWidth = anchorWidth + 2
  require(groupDataWidth > 0 && placementZeros >= 0)
  require(PEGroupContract.anchorToDataLatency == 1)
  private def named[T <: Data](value: T, stage: Int, name: String): T =
    value.suggestName(f"s${stage}%02d_${name}_q")

  val io = IO(new Bundle {
    val in_anchors = Flipped(Vec(groupCount, Valid(SInt(anchorWidth.W))))
    val in_groups = Flipped(Vec(groupCount, Valid(new PEGroupOutput(groupDataWidth))))
    val in_top_anchor_offset = Input(SInt(anchorWidth.W))
    val out_data = Valid(new PEDotResult(outDataWidth))
  })
  private val anchor_valid = io.in_anchors.head.valid
  io.in_anchors.foreach(source => assert(source.valid === anchor_valid,
    "All PEGroup anchors must follow one fixed schedule"))

  // S07: PG anchors now arrive at S06, after the local sum's zero test.
  // All-zero inputs use a safe internal base; the sentinel is not an exponent
  // to which a negative family offset may be added.
  private val zero_anchor = (-(BigInt(1) << (anchorWidth - 1))).S(anchorWidth.W)
  private val anchors = VecInit(io.in_anchors.map(_.bits))
  private val (max_anchor, max_index) = MaxLaneAlign.maximum(anchors.toSeq)
  private val selected_anchor = Mux(max_anchor === zero_anchor, 0.S(anchorWidth.W), max_anchor)
  private val s07_valid_q = named(RegNext(anchor_valid, false.B), 7, "valid")
  private val s07_anchors_q = named(RegEnable(anchors, anchor_valid), 7, "anchors")
  private val s07_max_anchor_q = named(RegEnable(selected_anchor, anchor_valid), 7, "max_anchor")
  private val s07_max_index_q = named(RegEnable(max_index, anchor_valid), 7, "max_index")
  io.in_groups.foreach(source => assert(source.valid === s07_valid_q,
    "PEGroup data and MidGroup control must meet without waiting"))

  // S07 -> S08: compute saturated deltas and align the matching PG data.
  // This replaces the old separate delta stage and metadata wait register.
  private val shifts = VecInit((0 until groupCount).map { index =>
    val delta = (s07_max_anchor_q.pad(calcWidth) - s07_anchors_q(index).pad(calcWidth)).asUInt
    Mux(s07_anchors_q(index) === zero_anchor, 0.U(shiftWidth.W),
      Mux(delta >= alignWidth.U, alignWidth.U(shiftWidth.W), delta(shiftWidth - 1, 0)))
  })
  // The complete N-way sum needs log2Ceil(N) carry bits: W41 for two
  // PEGroups, W42 for four. Its raw anchor follows that internal coordinate.
  private val raw_top_wide = s07_max_anchor_q.pad(calcWidth) +
    io.in_top_anchor_offset.pad(calcWidth) + carryBits.S(calcWidth.W)
  private val raw_top = raw_top_wide.asUInt(anchorWidth - 1, 0).asSInt
  when(s07_valid_q) { assert(raw_top.pad(calcWidth) === raw_top_wide) }

  // S08: exact placement and N-1 dynamic shifters; MAX has only wiring/MUX.
  private val placed = io.in_groups.map(source =>
    PEMath.placeAtAddTopExact(source.bits.mul_scale_mant, groupDataWidth, alignWidth)).toSeq
  private val (aligned, correction) = MaxLaneAlign.withCorrections(
    placed, shifts.toSeq, s07_max_index_q, alignWidth)
  private val merged_special = SpecialValueFlags.mergeAdd(io.in_groups.map(_.bits.special))
  private val s08_valid_q = named(RegNext(s07_valid_q, false.B), 8, "valid")
  private val s08_data_q = named(RegEnable(aligned, s07_valid_q), 8, "aligned")
  private val s08_correction_q = named(RegEnable(correction, s07_valid_q), 8, "correction")
  private val s08_raw_top_q = named(RegEnable(raw_top, s07_valid_q), 8, "raw_top")
  private val s08_special_q = named(RegEnable(merged_special, s07_valid_q), 8, "special")

  // S09: fuse the RTZ correction count with all operands before the final
  // CPA. The following abs/LZD still sees the exact same signed sum.
  private val exact_sum = CarrySave.sumWithCorrection(
    s08_data_q.toSeq, s08_correction_q, sumDataWidth)
  require(exact_sum.getWidth == sumDataWidth)
  private val s09_valid_q = named(RegNext(s08_valid_q, false.B), 9, "valid")
  private val s09_sum_q = named(RegEnable(exact_sum, s08_valid_q), 9, "sum")
  private val s09_raw_top_q = named(RegEnable(s08_raw_top_q, s08_valid_q), 9, "raw_top")
  private val s09_special_q = named(RegEnable(s08_special_q, s08_valid_q), 9, "special")

  // S10/S11: safe abs/LZD, then lossless normalization and anchor correction.
  private val normalize = Module(new PENormalizeExact(
    PENormalizeExactConfig(sumDataWidth, anchorWidth, firstStage = 10)))
  normalize.io.in_data.valid := s09_valid_q
  normalize.io.in_data.bits.result := s09_sum_q
  normalize.io.in_data.bits.raw_top_anchor := s09_raw_top_q
  normalize.io.in_data.bits.special := s09_special_q
  io.out_data.valid := normalize.io.out_data.valid
  // Losslessly extend the normalized internal S1/I1/F39 magnitude to the
  // public S1/I1/F40 coordinate. The leading-bit exponent stays unchanged.
  io.out_data.bits.magnitude := (if (sumDataWidth < outDataWidth)
    Cat(normalize.io.out_data.bits.magnitude, 0.U((outDataWidth - sumDataWidth).W))
    else normalize.io.out_data.bits.magnitude)
  io.out_data.bits.negative := normalize.io.out_data.bits.negative
  io.out_data.bits.top_anchor := normalize.io.out_data.bits.normalized_top_anchor
  io.out_data.bits.is_zero := normalize.io.out_data.bits.is_zero
  io.out_data.bits.special := normalize.io.out_data.bits.special
  if (groupCount == 2) {
    when(io.out_data.valid) {
      assert(!io.out_data.bits.magnitude(0), "g2 final magnitude must append one exact low zero")
    }
  }
}

/* Public output contract, all supported families: W = S + I + F.
 * FP16/BF16/E5M2/E4M3/E3M2/E2M3/E2M1/NVFP4/HiF4:
 * W = Design.dotCAddWidth + 2 = 42 by default; S=1, I=1, F=W-2=40.
 * The common top anchor is the exponent of magnitude bit W-2:
 * value = (-1)^midNegative * midMagnitude * 2^(topAnchor-(W-2)).
 * Normalization is lossless; sign plus magnitude occupy W bits in total.
 * Zero uses isZero and the minimum anchor sentinel. No backpressure.
 */
