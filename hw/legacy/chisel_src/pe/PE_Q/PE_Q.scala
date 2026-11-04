package dp.pe.q

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** 32-lane direct global alignment PE; independent H/Q optimization.
  * Product clusters keep the g4 hierarchy but have no local MAX/align/sum.
  * S11 public result, II=1; stable cfg, valid reset, payload hold on bubbles.
  * Final finite-window output RTZ and all alignment widths are specified explicitly.
  */
class PE_Q(alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_Q_g4"), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val pe_groups = Seq.fill(4)(Module(new PEGroup_Q(alignment)))
  private val reduction = Module(new PEGlobalAlignNormalize("Q", alignment))
  PEWiring.connectInputs(io, pe_groups.map(_.io.in_data), config)
  for ((group, index) <- pe_groups.zipWithIndex) reduction.io.in_products(index) <> group.io.out_data
  // All 32 Q elements share one E8M0 block scale per operand. Hoist it
  // outside lane deltas, then attach the common exponent to the global MAX.
  private val a_scale = io.in_data.bits.a.sf.sf_data(0)
  private val b_scale = io.in_data.bits.b.sf.sf_data(0)
  private val scale_exp = (Mux(a_scale.andR, 127.U(8.W), a_scale) +&
    Mux(b_scale.andR, 127.U(8.W), b_scale)).zext - 254.S
  private val s01_valid_q = RegNext(io.in_data.valid, false.B)
  private val s01_scale_exp_q = RegEnable(scale_exp, io.in_data.valid)
  private val s02_scale_exp_q = RegEnable(s01_scale_exp_q, s01_valid_q)
  reduction.io.in_anchor_offset := s02_scale_exp_q
  io.out_data <> reduction.io.out_data
}
