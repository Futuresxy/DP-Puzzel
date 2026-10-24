package dp.pe.hqe

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** HQE PE: input/scale distribution and complete PE-level reduction live here.
  * PEGroup_HQE/SubPE_HQE retain the existing local arithmetic and reuse.
  * PG anchor S06, data S07; PE MAX S07, alignment S08, sum S09, normalize S10/S11.
  * II=1, Valid-only; cfg stable through drain, valid resets, payload holds on bubbles.
  * Finite RTZ at local/PE aligners is distinct from lossless final normalization.
  */
class PE_HQE(alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_HQE_g4"), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val groupDataWidth = PEGroup_HQEContract.outputWidth(alignment)
  private val alignWidth = alignment.peAlignWidth
  private val anchorWidth = PEContract.anchorWidth
  private val outDataWidth = alignment.peResultWidth
  private val carryBits = log2Ceil(groupCount)
  private val sumDataWidth = alignWidth + carryBits
  private val placementZeros = alignWidth - groupDataWidth
  private val shiftWidth = log2Ceil(alignWidth + 1)
  private val calcWidth = anchorWidth + 2
  require(groupCount == 2 || groupCount == 4)
  require(groupDataWidth > 0 && placementZeros >= 0)
  require(PEGroupContract.anchorToDataLatency == 1)

  // S00-S07: keep the family's existing PG/SubPE modules. Every PG receives
  // four packed words; mode-specific block scale selection is visible below.
  private val pe_groups = Seq.fill(groupCount)(Module(new PEGroup_HQE(alignment)))
  // S00: cfg owns element/scale types; nested input tags are not controls.
  // cfg remains stable until the batch has drained. There is no backpressure.
  private val input_legal = Precision.hqe.supportsDataType(io.in_cfg.data_type) &&
    Precision.hqe.supportsDataType(io.in_cfg.b_data_type) &&
    FormatCompat.legalABPair(io.in_cfg.data_type, io.in_cfg.b_data_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.data_type, io.in_cfg.sf_type) &&
    FormatCompat.legalDataScalePair(io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
  when(io.in_data.valid) { assert(input_legal, "PE requires legal supported A/B and scale formats") }
  private val input_fire = io.in_data.valid && input_legal
  for ((group, index) <- pe_groups.zipWithIndex) {
    group.io.in_data.valid := input_fire
    for ((out, in, data_type, sf_type) <- Seq(
      (group.io.in_data.bits.a, io.in_data.bits.a, io.in_cfg.data_type, io.in_cfg.sf_type),
      (group.io.in_data.bits.b, io.in_data.bits.b, io.in_cfg.b_data_type, io.in_cfg.b_sf_type))) {
      out.data := VecInit(in.data.slice(index * 4, index * 4 + 4))
      out.data_type := data_type
      out.sf.sf_type := sf_type
      // MX Q/HiF4 use slot0; MXFP4 uses 0/0/1/1; NVFP4 uses 0/1/2/3.
      // The g2 profile takes the first two PG mappings from the same contract.
      val scale_index = Mux(data_type === DataType.nvfp4, index.U(log2Ceil(groupCount).W),
        Mux(data_type === DataType.e2_m1, (index / 2).U(log2Ceil(groupCount).W), 0.U(log2Ceil(groupCount).W)))
      out.sf.sf_data(0) := in.sf.sf_data(scale_index)
      out.sf.sf_group0 := VecInit(in.sf.sf_group0.slice(index * 4, index * 4 + 4))
      out.sf.sf_group1 := VecInit(in.sf.sf_group1.slice(index * 2, index * 2 + 2))
    }
  }
  private val pg_anchors = VecInit(pe_groups.map(_.io.out_pegroup_anchor))
  private val pg_data = VecInit(pe_groups.map(_.io.out_pegroup_data))
  private val product_type = FormatCompat.canonicalProductType(io.in_cfg.data_type, io.in_cfg.b_data_type)
  // PG raw anchor -> exponent of magnitude bit W-2: I - 2*bias - 1.
  // Q element exponents have already been rebased to E5/bias15 by unpacking.
  private val top_anchor_offset = MuxLookup(product_type, 0.S(11.W))(Seq(
    DataType.fp16 -> (-27).S(11.W),   // I4 - 2*15 - 1
    DataType.bf16 -> (-251).S(11.W), // I4 - 2*127 - 1
    DataType.e5_m2 -> (-26).S(11.W), DataType.e4_m3 -> (-26).S(11.W),
    DataType.e3_m2 -> (-26).S(11.W), DataType.e2_m3 -> (-26).S(11.W),
    DataType.e2_m1 -> 9.S(11.W), DataType.nvfp4 -> 12.S(11.W), DataType.hi_f4 -> 10.S(11.W)))

  private val anchor_valid = pg_anchors.head.valid
  pg_anchors.foreach(source => assert(source.valid === anchor_valid,
    "All PEGroup anchors must follow one fixed schedule"))

  // S07: PG anchors now arrive at S06, after the local sum's zero test.
  // All-zero inputs use a safe internal base; the sentinel is not an exponent
  // to which a negative family offset may be added.
  private val zero_anchor = (-(BigInt(1) << (anchorWidth - 1))).S(anchorWidth.W)
  private val anchors = VecInit(pg_anchors.map(_.bits.pegroup_anchor))
  private val (max_anchor, max_index) = MaxLaneAlign.maximum(anchors.toSeq)
  private val selected_anchor = Mux(max_anchor === zero_anchor, 0.S(anchorWidth.W), max_anchor)
  private val s07_valid_q = RegNext(anchor_valid, false.B)
  private val s07_anchors_q = RegEnable(anchors, anchor_valid)
  private val s07_max_anchor_q = RegEnable(selected_anchor, anchor_valid)
  private val s07_max_index_q = RegEnable(max_index, anchor_valid)
  pg_data.foreach(source => assert(source.valid === s07_valid_q,
    "PEGroup data and PE control must meet without waiting"))

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
    top_anchor_offset.pad(calcWidth) + carryBits.S(calcWidth.W)
  private val raw_top = raw_top_wide.asUInt(anchorWidth - 1, 0).asSInt
  when(s07_valid_q) { assert(raw_top.pad(calcWidth) === raw_top_wide) }

  // S08: exact placement and N-1 dynamic shifters; MAX has only wiring/MUX.
  private val placed = pg_data.map(source =>
    (if (placementZeros == 0) source.bits.mul_scale_mant
      else Cat(source.bits.mul_scale_mant.asUInt, 0.U(placementZeros.W)).asSInt)).toSeq
  private val (aligned, correction) = MaxLaneAlign.withCorrections(
    placed, shifts.toSeq, s07_max_index_q, alignWidth)
  private val merged_special = SpecialValueFlags.mergeAdd(pg_data.map(_.bits.special))
  private val s08_valid_q = RegNext(s07_valid_q, false.B)
  private val s08_data_q = RegEnable(aligned, s07_valid_q)
  private val s08_correction_q = RegEnable(correction, s07_valid_q)
  private val s08_raw_top_q = RegEnable(raw_top, s07_valid_q)
  private val s08_special_q = RegEnable(merged_special, s07_valid_q)

  // S09: fuse the RTZ correction count with all operands before the final
  // CPA. The following abs/LZD still sees the exact same signed sum.
  private val exact_sum = CarrySave.sumWithCorrection(
    s08_data_q.toSeq, s08_correction_q, sumDataWidth)
  require(exact_sum.getWidth == sumDataWidth)
  private val s09_valid_q = RegNext(s08_valid_q, false.B)
  private val s09_sum_q = RegEnable(exact_sum, s08_valid_q)
  private val s09_raw_top_q = RegEnable(s08_raw_top_q, s08_valid_q)
  private val s09_special_q = RegEnable(s08_special_q, s08_valid_q)

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
