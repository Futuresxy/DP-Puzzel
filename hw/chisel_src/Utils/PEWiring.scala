package dp.utils

import chisel3._
import chisel3.util._
import dp.config._

/** Wiring only: no hidden state, data-path stages, or extra Module layer. */
object PEWiring {
  def connectInput(io: PEIO, groups: Seq[PEGroupBase], config: PEConfig): Unit =
    connectInputs(io, groups.map(_.io.in_data), config)
  def connectInputs(io: PEIO, inputs: Seq[ValidIO[PEGroupInput]], config: PEConfig): Unit = {
    require(inputs.size == config.groupCount)
    val supported = config.precision.supportsDataType(io.in_cfg.data_type) &&
      config.precision.supportsDataType(io.in_cfg.b_data_type) &&
      FormatCompat.legalABPair(io.in_cfg.data_type, io.in_cfg.b_data_type) &&
      FormatCompat.legalDataScalePair(io.in_cfg.data_type, io.in_cfg.sf_type) &&
      FormatCompat.legalDataScalePair(io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
    when(io.in_data.valid) { assert(supported, "PE requires a supported stable configuration") }
    for ((input, index) <- inputs.zipWithIndex) {
      input.valid := io.in_data.valid && supported
      def operand(out: VectorInputBundle, in: VectorInputBundle, dataType: UInt, sfType: UInt): Unit = {
        out.data := VecInit(in.data.slice(index * 4, index * 4 + 4))
        out.data_type := dataType
        out.sf.sf_type := sfType
        out.sf.sf_data(0) := in.sf.sf_data(PEMath.localScaleIndex(index, dataType, config.groupCount))
        out.sf.sf_group0 := VecInit(in.sf.sf_group0.slice(index * 4, index * 4 + 4))
        out.sf.sf_group1 := VecInit(in.sf.sf_group1.slice(index * 2, index * 2 + 2))
      }
      operand(input.bits.a, io.in_data.bits.a, io.in_cfg.data_type, io.in_cfg.sf_type)
      operand(input.bits.b, io.in_data.bits.b, io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
    }
  }
  def connectResults(io: PEIO, groups: Seq[PEGroupBase], reduction: PEAlignNormalize): Unit = {
    for ((group, index) <- groups.zipWithIndex) {
      reduction.io.in_anchors(index).valid := group.io.out_pegroup_anchor.valid
      reduction.io.in_anchors(index).bits := group.io.out_pegroup_anchor.bits.pegroup_anchor
      reduction.io.in_groups(index) <> group.io.out_pegroup_data
    }
    io.out_data <> reduction.io.out_data
  }
}
