package dp.pe.q

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** Four word product clusters; no PG-local MAX, alignment, or sum.
  * 8 products meet the other clusters at the PE's single global alignment.
  * S01 decode, S02 raw products; II=1, valid reset, payload enable/hold.
  */
class PEGroup_Q(alignment: AlignmentConfig = AlignmentConfig()) extends Module {
  override def desiredName: String = "PEGroup_Q" + alignment.suffix
  private val cfg = SubPEConfig.forFamily("Q", alignment)
  val io = IO(new RawGroupIO(8, 8))
  private val unpacker = Module(new DataUnpack_Q(4, 1, 4, 2, cfg.expWidth, cfg.mantWidth, cfg.signGroupWidth))
  unpacker.io.in_data <> io.in_data
  private val unpacked = unpacker.io.out_data
  private val ua = unpacked.bits.pegroup_unpack_a
  private val ub = unpacked.bits.pegroup_unpack_b
  private val sub_pes = Seq.fill(4)(Module(new SubPE_Q(alignment)))
  for ((sub_pe, index) <- sub_pes.zipWithIndex) {
    sub_pe.io.in_data.valid := unpacked.valid
    sub_pe.io.in_data.bits.a_exp := ua.pegroup_exp_o.pegroup_exp_o(index)
    sub_pe.io.in_data.bits.b_exp := ub.pegroup_exp_o.pegroup_exp_o(index)
    sub_pe.io.in_data.bits.a_mant := ua.pegroup_mant_o.pegroup_mant_o(index)
    sub_pe.io.in_data.bits.b_mant := ub.pegroup_mant_o.pegroup_mant_o(index)
    sub_pe.io.in_data.bits.a_sign := ua.pegroup_sign_o.pegroup_sign_o(index)
    sub_pe.io.in_data.bits.b_sign := ub.pegroup_sign_o.pegroup_sign_o(index)
    sub_pe.io.in_data.bits.ab_type := FormatCompat.canonicalProductType(
      ua.pegroup_exp_o.pegroup_type_o, ub.pegroup_exp_o.pegroup_type_o)
  }
  private val s02_valid_q = RegNext(unpacked.valid, false.B)
  private val s02_special_q = RegEnable(unpacked.bits.pegroup_special, unpacked.valid)
  for ((sub_pe, index) <- sub_pes.zipWithIndex) {
    assert(sub_pe.io.out_data.valid === s02_valid_q)
    for (lane <- 0 until 2) {
      val outIndex = index * 2 + lane
      val source = sub_pe.io.out_data.bits
      io.out_data.bits.magnitude(outIndex) := source.magnitude(lane)
      io.out_data.bits.negative(outIndex) := source.negative(lane)
      io.out_data.bits.is_zero(outIndex) := source.is_zero(lane)
      io.out_data.bits.top_anchor(outIndex) := source.top_anchor(lane)
    }
  }
  io.out_data.valid := s02_valid_q
  io.out_data.bits.special := s02_special_q
}
