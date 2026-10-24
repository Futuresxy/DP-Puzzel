package dp.pe.e

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

object PEGroup_EContract {
  def localAlignPadWidth(p: AlignmentConfig): Int = p.groupGuardBits
  def outputWidth(p: AlignmentConfig): Int = 20 + p.groupGuardBits
  def topAnchorOffset(dataType: UInt): SInt =
    Mux(dataType === DataType.hi_f4, 10.S(6.W), 12.S(6.W))
}

/** FP4-family PEGroup: MXFP4, NVFP4, and HiF4 share one exact narrow datapath. */
class PEGroup_E(alignment: AlignmentConfig = AlignmentConfig()) extends PEGroupBase(
  4, 1, 4, 2, PEGroup_EContract.outputWidth(alignment)
) {
  override def desiredName: String = "PEGroup_E" + alignment.suffix
  private val cfg = SubPEConfig.forFamily("E", alignment)
  private val scaleProductWidth = 8
  private val pairWidth = cfg.outWidth + 1                              // 12
  private val alignedWidth = pairWidth + PEGroup_EContract.localAlignPadWidth(alignment) // 14
  private val sumWidth = alignedWidth + 1                               // 15
  private val fullScaleWidth = sumWidth + scaleProductWidth + 1          // 24
  private val exactStructuralDrop = math.max(0, fullScaleWidth - outputWidth)
  private val outputLsbZeros = math.max(0, outputWidth - fullScaleWidth)
  private val provenStructuralZeros =
    (cfg.outWidth - 11) + PEGroup_EContract.localAlignPadWidth(alignment)

  require(exactStructuralDrop <= provenStructuralZeros,
    s"FP4 output drops $exactStructuralDrop bits, but only $provenStructuralZeros are proven structural zeros")

  // The input offer is S00; raw operands and scale metadata register at S01.
  // Decode after that register, matching the FP8/FP6 input-stage boundary.
  // All families share the S02-S07 compute schedule without result stalls.
  private val unpacker = Module(new DataUnpack_E(
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
  private val sub_pes = Seq.fill(dimk)(Module(new SubPE_E(alignment)))
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
  // Adjacent SubPEs share g1; E2M1/NVFP4 anchors are all zero. Carry only
  // the two distinct anchors, alongside the existing three-clock SubPE path.
  private val input_anchors = VecInit(Seq(0, 2).map(index =>
    ua.pegroup_exp_o.pegroup_exp_o(index) +& ub.pegroup_exp_o.pegroup_exp_o(index)))
  private val s02_direct_anchors_q = RegEnable(input_anchors, input_valid)
  private val sub_anchors = s02_direct_anchors_q

  // S03: compare the two pair anchors; unbias scale exponent.
  private val hi_is_max = sub_anchors(1) > sub_anchors(0)
  private val max_anchor = Mux(hi_is_max, sub_anchors(1), sub_anchors(0))
  private val shift = Mux(hi_is_max, sub_anchors(1) - sub_anchors(0), sub_anchors(0) - sub_anchors(1))
  private val s03_max_anchor_q = RegEnable(max_anchor, s02_valid_q)
  private val s03_hi_is_max_q = RegEnable(hi_is_max, s02_valid_q)
  private val s03_shift_q = RegEnable(shift, s02_valid_q)
  private val s03_scale_exp_q = RegEnable(s02_scale_exp_sum_q.zext - 254.S, s02_valid_q)
  private val s03_special_q = RegEnable(s02_special_q, s02_valid_q)
  private val s03_scale_mant_q = RegEnable(s02_scale_mant_q, s02_valid_q)

  // S04: internal raw anchor and shift controls arrive with the three-clock SubPE result.
  private val s04_shift_q = RegEnable(s03_shift_q, s03_valid_q)
  private val s04_hi_is_max_q = RegEnable(s03_hi_is_max_q, s03_valid_q)
  when(s03_valid_q) { assert(s03_shift_q <= PEGroup_EContract.localAlignPadWidth(alignment).U) }
  private val s04_special_q = RegEnable(s03_special_q, s03_valid_q)
  private val s04_anchor_q = RegEnable(
    PEGroupMath.resizeSInt(s03_max_anchor_q.zext +& s03_scale_exp_q, anchorWidth), s03_valid_q)
  private val s04_scale_mant_q = RegEnable(s03_scale_mant_q, s03_valid_q)

  // S05: exact same-anchor preadds, then one 0/1/2-bit arithmetic shifter.
  // The two appended zeros guarantee that no nonzero bit is shifted out.
  sub_pes.foreach(subPE => assert(subPE.io.out_data.valid === s04_valid_q,
    "SubPE result and PEGroup shifts must arrive on the same clock"))
  private val pair_lo = sub_pes(0).io.out_data.bits.result +& sub_pes(1).io.out_data.bits.result
  private val pair_hi = sub_pes(2).io.out_data.bits.result +& sub_pes(3).io.out_data.bits.result
  require(pair_lo.getWidth == pairWidth && pair_hi.getWidth == pairWidth)
  private val max_pair = Mux(s04_hi_is_max_q, pair_hi, pair_lo)
  private val min_pair = Mux(s04_hi_is_max_q, pair_lo, pair_hi)
  private val padded_min = PEGroupMath.appendZeros(min_pair, PEGroup_EContract.localAlignPadWidth(alignment))
  private val aligned_min = padded_min >> s04_shift_q
  private val s05_max_pair_q = RegEnable(max_pair, s04_valid_q)
  private val s05_aligned_min_q = RegEnable(aligned_min, s04_valid_q)
  private val s05_special_q = RegEnable(s04_special_q, s04_valid_q)
  private val s05_scale_mant_q = RegEnable(s04_scale_mant_q, s04_valid_q)

  // S06: complete the two-pair sum. MAX's low zeros are wiring, not registers.
  private val aligned_max = PEGroupMath.appendZeros(s05_max_pair_q, PEGroup_EContract.localAlignPadWidth(alignment))
  private val sum = aligned_max +& s05_aligned_min_q
  require(sum.getWidth == sumWidth)
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

  // S07: all formats use the decoded scale mantissa. E8M0 is 8*8=64 in
  // the common F6 coefficient domain, including mixed E2M1/NVFP4 products.
  private val scale_product = PEGroupMath.resizeSInt(s06_sum_q * s06_scale_mant_q.zext, fullScaleWidth)
  private val result = if (exactStructuralDrop > 0) {
    scale_product.asUInt(fullScaleWidth - 1, exactStructuralDrop).asSInt
  } else {
    PEGroupMath.appendZeros(scale_product, outputLsbZeros)
  }
  when(s06_valid_q) {
    if (exactStructuralDrop > 0) assert(!scale_product.asUInt(exactStructuralDrop - 1, 0).orR)
  }
  private val s07_result_q = RegEnable(result, s06_valid_q)
  private val s07_special_q = RegEnable(s06_special_q, s06_valid_q)
  io.out_pegroup_data.valid := s07_valid_q
  io.out_pegroup_data.bits.mul_scale_mant := s07_result_q
  io.out_pegroup_data.bits.special := s07_special_q
}

/* Output fixed-point contract: W = S + I + F; I excludes sign.
 * Format       W(default) S I  F(default) F for configured W
 * E2M1/NVFP4   22         1 13 8          W-14
 * HiF4         22         1 11 10         W-12
 * Exact W11 SubPE -> W12 pair sum -> W14 alignment -> W15 sum -> W24 scale product.
 * The W24->W22 boundary drops only proven structural zeros. E2M1 is placed
 * at the same I13 coordinate as NVFP4 through the unit scale mantissa.
 * Anchor S06, data S07; the common MidGroup path produces S11 directly.
 */
