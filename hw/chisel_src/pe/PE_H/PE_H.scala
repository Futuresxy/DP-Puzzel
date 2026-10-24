package dp.pe.h

import chisel3._
import dp.config._
import dp.utils._

/** 16-lane direct global alignment PE; independent H/Q optimization.
  * Product clusters keep the g4 hierarchy but have no local MAX/align/sum.
  * S11 public result, II=1; stable cfg, valid reset, payload hold on bubbles.
  * Final finite-window output RTZ and all alignment widths are specified explicitly.
  */
class PE_H(alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_H_g4"), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val pe_groups = Seq.fill(4)(Module(new PEGroup_H(alignment)))
  private val reduction = Module(new PEGlobalAlignNormalize("H", alignment))
  PEWiring.connectInputs(io, pe_groups.map(_.io.in_data), config)
  for ((group, index) <- pe_groups.zipWithIndex) reduction.io.in_products(index) <> group.io.out_data
  reduction.io.in_anchor_offset := 0.S
  io.out_data <> reduction.io.out_data
}
