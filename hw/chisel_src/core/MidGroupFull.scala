package dp.core

import dp.config._
import dp.pe._
import chisel3._
import chisel3.util._

/** Four complete PEGroups share the S08-S11 reduction and exact normalization.
  * Accepts one Valid packed H16/Q32/E64 vector each cycle; latency 11 stages.
  * in_cfg must remain stable until the pipeline drains. No backpressure.
  * Reset clears valid; unreset data registers hold on bubbles. Output is
  * magnitude/sign/top-anchor after finite-window RTZ inter-group alignment.
  */
class MidGroupFull(alignWidth: Int = Design.dotCAddWidth) extends MidGroupBase(alignWidth) {
  override def desiredName: String = s"MidGroupFull_H16Q32E64_W${alignWidth}"
  private val groupCount = MidGroupContract.groupCount
  private val groups = Seq.fill(groupCount)(Module(new PEGroupFull))
  private val reduction = Module(new MidGroupAlignNormalize(
    PEGroupFullContract.outputWidth, alignWidth = alignWidth
  ))

  private val input_supported =
    PEPrecisionConfigs.fullSupport.supportsDataType(io.in_cfg.data_type) &&
      PEPrecisionConfigs.fullSupport.supportsDataType(io.in_cfg.b_data_type) &&
      PETileMath.legalABPair(io.in_cfg.data_type, io.in_cfg.b_data_type) &&
      PETileMath.legalDataScalePair(io.in_cfg.data_type, io.in_cfg.sf_type) &&
      PETileMath.legalDataScalePair(io.in_cfg.b_data_type, io.in_cfg.b_sf_type)
  when(io.in_data.valid) {
    assert(input_supported, "MidGroupFull requires a supported stable batch configuration")
  }

  for ((group, index) <- groups.zipWithIndex) {
    val data_start = index * groupSize
    val group1_start = index * (groupSize / 2)
    val a_scale_index = PETileMath.localScaleIndex(index, io.in_cfg.data_type)
    val b_scale_index = PETileMath.localScaleIndex(index, io.in_cfg.b_data_type)
    group.io.in_data.valid := io.in_data.valid && input_supported

    def connectOperand(
      groupInput: VectorInputBundle,
      midInput: VectorInputBundle,
      dataType: UInt,
      sfType: UInt,
      scaleIndex: UInt
    ): Unit = {
      groupInput.data := VecInit(
        midInput.data.slice(data_start, data_start + groupSize)
      )
      groupInput.data_type := dataType
      groupInput.sf.sf_data(0) := midInput.sf.sf_data(scaleIndex)
      groupInput.sf.sf_type := sfType
      groupInput.sf.sf_group0 := VecInit(
        midInput.sf.sf_group0.slice(data_start, data_start + groupSize)
      )
      groupInput.sf.sf_group1 := VecInit(
        midInput.sf.sf_group1.slice(group1_start, group1_start + groupSize / 2)
      )
    }
    connectOperand(group.io.in_data.bits.a, io.in_data.bits.a,
      io.in_cfg.data_type, io.in_cfg.sf_type, a_scale_index)
    connectOperand(group.io.in_data.bits.b, io.in_data.bits.b,
      io.in_cfg.b_data_type, io.in_cfg.b_sf_type, b_scale_index)

    reduction.io.in_anchors(index).valid := group.io.out_pegroup_anchor.valid
    reduction.io.in_anchors(index).bits :=
      group.io.out_pegroup_anchor.bits.pegroup_anchor

    reduction.io.in_groups(index).valid := group.io.out_pegroup_data.valid
    reduction.io.in_groups(index).bits := group.io.out_pegroup_data.bits
  }

  reduction.io.in_top_anchor_offset :=
    (-FixedPointMeta.dataBias2x(
      PETileMath.canonicalProductType(io.in_cfg.data_type, io.in_cfg.b_data_type), anchorWidth) +
      FixedPointMeta.pegroupFullOutputIntBits(
        PETileMath.canonicalProductType(io.in_cfg.data_type, io.in_cfg.b_data_type)).zext - 1.S).pad(anchorWidth)
  io.out_mid_data <> reduction.io.out_data
}

/* Output W/S/I/F (I excludes sign):
 * Supported formats: FP16/BF16/E5M2/E4M3/E3M2/E2M3/E2M1/NVFP4/HiF4.
 * Every format: W=Design.dotCAddWidth+2 (default 42), S=1, I=1, F=W-2 (40).
 * S11 output is losslessly normalized; value = (-1)^midNegative * midMagnitude * 2^(midAnchor-F).
 * Fixed input-to-output latency 11 clocks; valid bubbles advance, no stalls.
 */
