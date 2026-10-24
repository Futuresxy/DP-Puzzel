package dp.pe.qe

import dp.config._
import dp.utils._
import chisel3._
import chisel3.util._

/** Fixed family-local boundary used by Low PEGroup and MidGroup. */
object PEGroup_QEContract {
  def localAlignPadWidth(p: AlignmentConfig): Int = p.groupGuardBits + 0
  def outputWidth(p: AlignmentConfig): Int = SubPEConfig.forFamily("QE", p).outWidth + localAlignPadWidth(p) + 2
  def topAnchorOffset(dataType: UInt): SInt = FixedPointMeta.pegroupFullOutputIntBits(dataType).zext - FixedPointMeta.dataBias2x(dataType, 11) - 1.S
}

/** Runtime-low PEGroup: FP8/FP6 and all FP4 families, never FP16/BF16. */
class PEGroup_QE(alignment: AlignmentConfig = AlignmentConfig()) extends PEGroupBase(
  4, 1, 4, 2, PEGroup_QEContract.outputWidth(alignment)
) {
  override def desiredName: String = "PEGroup_QE" + alignment.suffix
  private val cfg = SubPEConfig.forFamily("QE", alignment)
  private val scaleProductWidth = FixedPointMeta.scaleMantProductWidth
  private val unitScaleProduct = 1 << (FixedPointMeta.scaleMantFracBits * 2)
  private val alignPadWidth = PEGroup_QEContract.localAlignPadWidth(alignment)
  private val alignedWidth = cfg.outWidth + alignPadWidth
  private val sumWidth = alignedWidth + log2Ceil(dimk)
  require(sumWidth == outputWidth)

  // The input offer is S00. Every family has one input register stage
  // before the S02-S07 compute path. No result ready can stall us.
  private val unpacker = Module(new DataUnpack_QE(
    dimk, numSF, numG0, numG1,
    expW = cfg.expWidth, mantW = cfg.mantWidth, signW = cfg.signGroupWidth
  ))
  unpacker.io.in_data <> io.in_data
  private val unpack_bits = unpacker.io.out_data.bits
  private val input_valid = unpacker.io.out_data.valid
  private val ua = unpack_bits.pegroup_unpack_a
  private val ub = unpack_bits.pegroup_unpack_b
  private val product_type = FormatCompat.canonicalProductType(
    ua.pegroup_exp_o.pegroup_type_o, ub.pegroup_exp_o.pegroup_type_o)
  private val sub_pes = Seq.fill(dimk)(Module(new SubPE_QE(alignment)))
  for ((subPE, index) <- sub_pes.zipWithIndex) {
    subPE.io.in_data.valid := input_valid
    subPE.io.in_data.bits.a_exp := ua.pegroup_exp_o.pegroup_exp_o(index)
    subPE.io.in_data.bits.b_exp := ub.pegroup_exp_o.pegroup_exp_o(index)
    subPE.io.in_data.bits.a_mant := ua.pegroup_mant_o.pegroup_mant_o(index)
    subPE.io.in_data.bits.b_mant := ub.pegroup_mant_o.pegroup_mant_o(index)
    subPE.io.in_data.bits.a_sign := ua.pegroup_sign_o.pegroup_sign_o(index)
    subPE.io.in_data.bits.b_sign := ub.pegroup_sign_o.pegroup_sign_o(index)
    subPE.io.in_data.bits.ab_type := product_type
  }

  private val s02_valid_q = RegNext(input_valid, false.B)
  private val s03_valid_q = RegNext(s02_valid_q, false.B)
  private val s04_valid_q = RegNext(s03_valid_q, false.B)
  private val s05_valid_q = RegNext(s04_valid_q, false.B)
  private val s06_valid_q = RegNext(s05_valid_q, false.B)
  private val s07_valid_q = RegNext(s06_valid_q, false.B)

  // S02: shared scale state in parallel with the SubPE products.
  private val scale_exp_sum = ua.pegroup_exp_o.pegroup_scaleexp_o(0) +&
    ub.pegroup_exp_o.pegroup_scaleexp_o(0)
  private val s02_scale_exp_sum_q = RegEnable(scale_exp_sum, input_valid)
  private val s02_special_q = RegEnable(unpack_bits.pegroup_special, input_valid)
  private val scale_mant_product = ua.pegroup_mant_o.pegroup_scalemant_o(0) *
    ub.pegroup_mant_o.pegroup_scalemant_o(0)
  private val s02_scale_mant_q = RegEnable(scale_mant_product, input_valid)
  private val s02_use_scale_q = RegEnable(
    product_type === DataType.nvfp4 || product_type === DataType.hi_f4, input_valid)
  private val sub_anchors = VecInit(sub_pes.map(_.io.out_anchor.bits.subpe_anchor))
  sub_pes.foreach(subPE => assert(subPE.io.out_anchor.valid === s02_valid_q,
    "SubPE early anchor must follow the fixed PEGroup schedule"))

  // S03: balanced MAX with winning channel; unbias scale exponent.
  private val (max_anchor, max_index) = MaxLaneAlign.maximum(sub_anchors.map(_.zext).toSeq)
  private val s03_max_anchor_q = RegEnable(max_anchor.asUInt, s02_valid_q)
  private val s03_max_index_q = RegEnable(max_index, s02_valid_q)
  private val s03_sub_anchors_q = RegEnable(sub_anchors, s02_valid_q)
  private val s03_scale_exp_q = RegEnable(s02_scale_exp_sum_q.zext - 254.S, s02_valid_q)
  private val s03_special_q = RegEnable(s02_special_q, s02_valid_q)
  private val s03_scale_mant_q = RegEnable(s02_scale_mant_q, s02_valid_q)
  private val s03_use_scale_q = RegEnable(s02_use_scale_q, s02_valid_q)

  // S04: internal raw anchor and shift controls arrive with the three-clock SubPE result.
  // Saturation at the carrier width is exact for signed RTZ and narrows controls.
  private val shiftWidth = log2Ceil(alignedWidth + 1)
  private val shifts = VecInit((0 until dimk).map { index =>
    val delta = s03_max_anchor_q - s03_sub_anchors_q(index)
    Mux(delta >= alignedWidth.U, alignedWidth.U(shiftWidth.W), delta.pad(shiftWidth)(shiftWidth - 1, 0))
  })
  private val s04_shifts_q = RegEnable(shifts, s03_valid_q)
  private val s04_max_index_q = RegEnable(s03_max_index_q, s03_valid_q)
  private val s04_special_q = RegEnable(s03_special_q, s03_valid_q)
  private val s04_anchor_q = RegEnable(
    PEGroupMath.resizeSInt(s03_max_anchor_q.zext +& s03_scale_exp_q, anchorWidth), s03_valid_q)
  private val s04_scale_mant_q = RegEnable(s03_scale_mant_q, s03_valid_q)
  private val s04_use_scale_q = RegEnable(s03_use_scale_q, s03_valid_q)

  // S05: MAX bypass plus three arithmetic aligners and a two-bit RTZ correction.
  sub_pes.foreach(subPE => assert(subPE.io.out_data.valid === s04_valid_q,
    "SubPE result and PEGroup shifts must arrive on the same clock"))
  private val padded = sub_pes.map(subPE =>
    PEGroupMath.appendZeros(subPE.io.out_data.bits.result, alignPadWidth))
  private val (aligned, correction) = MaxLaneAlign.withCorrections(
    padded, s04_shifts_q.toSeq, s04_max_index_q, alignedWidth)
  private val s05_aligned_q = RegEnable(aligned, s04_valid_q)
  private val s05_correction_q = RegEnable(correction, s04_valid_q)
  private val s05_special_q = RegEnable(s04_special_q, s04_valid_q)
  private val s05_scale_mant_q = RegEnable(s04_scale_mant_q, s04_valid_q)
  private val s05_use_scale_q = RegEnable(s04_use_scale_q, s04_valid_q)

  // S06: absorb RTZ corrections into the CSA sum; preserve both carry-growth bits.
  private val sum = CarrySave.sumWithCorrection(
    s05_aligned_q.toSeq, s05_correction_q, sumWidth)
  private val s06_sum_q = RegEnable(sum, s05_valid_q)

  // S06: publish the anchor only once the local sum is known. Keep the
  // original anchor for nonzero sums; zero must not win the MidGroup MAX.
  private val s05_anchor_q = RegEnable(s04_anchor_q, s04_valid_q)
  private val s06_anchor_q = RegEnable(s05_anchor_q, s05_valid_q)
  private val zero_anchor = (-(BigInt(1) << (anchorWidth - 1))).S(anchorWidth.W)
  io.out_pegroup_anchor.valid := s06_valid_q
  io.out_pegroup_anchor.bits.pegroup_anchor := Mux(s06_sum_q === 0.S, zero_anchor, s06_anchor_q)
  when(s06_valid_q && s06_sum_q =/= 0.S) {
    assert(s06_anchor_q > zero_anchor, "Nonzero PG anchor must not use the zero sentinel")
  }
  private val s06_special_q = RegEnable(s05_special_q, s05_valid_q)
  private val s06_scale_mant_q = RegEnable(s05_scale_mant_q, s05_valid_q)
  private val s06_use_scale_q = RegEnable(s05_use_scale_q, s05_valid_q)

  // S07: apply the family scale mantissa, or preserve the unit-scale sum.
  private val structuralZeros = cfg.outWidth - 11
  private val compact_sum = s06_sum_q.asUInt(sumWidth - 1, structuralZeros).asSInt
  private val coefficient = Mux(s06_use_scale_q, s06_scale_mant_q, 0.U(scaleProductWidth.W))
  private val scale_product = compact_sum * coefficient.zext
  private val restoredZeros = outputWidth - scale_product.getWidth
  require(restoredZeros >= 0)
  private val scaled_output = PEGroupMath.appendZeros(scale_product, restoredZeros)
  private val result = Mux(s06_use_scale_q, scaled_output, s06_sum_q)
  when(s06_valid_q) {
    when(s06_use_scale_q) {
      assert(!s06_sum_q.asUInt(structuralZeros - 1, 0).orR,
        "Compact scale multiplication may discard only structural FP4 zeros")
    }.otherwise { assert(s06_scale_mant_q === unitScaleProduct.U) }
  }
  private val s07_result_q = RegEnable(result, s06_valid_q)
  private val s07_special_q = RegEnable(s06_special_q, s06_valid_q)
  io.out_pegroup_data.valid := s07_valid_q
  io.out_pegroup_data.bits.mul_scale_mant := s07_result_q
  io.out_pegroup_data.bits.special := s07_special_q
}

/* Output fixed-point contract: W = S + I + F; I excludes sign.
 * Format                 W(default) S I  F(default) F for configured W
 * E5M2/E4M3/E3M2/E2M3     33         1 5  27         W-6
 * E2M1                   33         1 10 22         W-11
 * NVFP4                  33         1 13 19         W-14
 * HiF4                   33         1 11 21         W-12
 * W = Design.subpe_outWidth + 2 alignment bits + 2 sum bits = 33.
 * Anchor S06, data S07; fixed distance 1 clock, no backpressure.
 */
