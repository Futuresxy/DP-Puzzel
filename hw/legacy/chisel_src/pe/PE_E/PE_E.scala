package dp.pe.e

import chisel3._
import dp.config._
import dp.utils._

/** E scaled dot PE; 4 SubPEs per PG, normalized output at S11, II=1.
  * Stable batch cfg, Valid-only; reset clears valid, data registers hold on bubbles.
  * Finite alignment RTZ is distinct from the final lossless normalization.
  */
class PE_E(groupCount: Int = 4, alignment: AlignmentConfig = AlignmentConfig())
  extends PEBase(PEConfig("PE_E_g" + groupCount), alignment) {
  override def desiredName: String = config.profile + alignment.suffix
  private val pe_groups = Seq.fill(config.groupCount)(Module(new PEGroup_E(alignment)))
  private val reduction = Module(new PEAlignNormalize(
    PEGroup_EContract.outputWidth(alignment), config.groupCount, alignment))
  PEWiring.connectInput(io, pe_groups, config)
  PEWiring.connectResults(io, pe_groups, reduction)
  private val product_type = FormatCompat.canonicalProductType(io.in_cfg.data_type, io.in_cfg.b_data_type)
  reduction.io.in_top_anchor_offset := PEGroup_EContract.topAnchorOffset(product_type).pad(11)
}
