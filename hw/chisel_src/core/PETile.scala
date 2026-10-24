package dp.core
import dp.config._
import dp.common.MaxLaneAlign
import dp.pe._
import chisel3._
import chisel3.util._
/** Full reuse dot+C unit, retaining PETile -> MidGroup -> PEGroup -> SubPE.
  * Configuration is accepted only while idle and held through result.last.
  * AB/C are admitted atomically; each accepted pair produces one FP32 result
  * after 18 register stages. Initiation interval is one cycle within a batch.
  * Internal/output Valid pipelines cannot stall. Reset clears control/valid;
  * data registers hold on bubbles and are intentionally not reset.
  * Finite-window RTZ alignment precedes configurable final FP32 rounding.
  * See hw/spec/core/PETile.md for scale layout and numerical limits.
  */
class PETile(
  dimk: Int = Resource.dimK,
  groupSize: Int = Resource.groupDimK,
  alignWidth: Int = Design.dotCAddWidth
) extends Module {
  override def desiredName: String = s"PETile_H${dimk}Q${2 * dimk}E${4 * dimk}${if (alignWidth == 40) "" else s"_W${alignWidth}"}"
  require(alignWidth >= 40 && alignWidth <= 64, "Full alignment window must be 40..64 bits")
  require(dimk >= 16 && dimk <= 64 && dimk % 16 == 0,
    s"PETile dimk=$dimk must contain 1..4 Full MidGroups (16 words each)")
  require(groupSize == Resource.groupDimK,
    s"PETile groupSize=$groupSize must be ${Resource.groupDimK}")
  val io = IO(new Bundle {
    val in_cfg = Flipped(Decoupled(new PETileConfig))
    val in_ab   = Flipped(Decoupled(new PETileABInput(dimk)))
    val in_c    = Flipped(Decoupled(new PETileCInput))
    val out_result = Valid(new PETileOutput)
    val out_idle = Output(Bool())
  })

  /* 按照输入数据个数和对应的PE Group支持的计算大小，进行划分
  * 每个PEgroup 支持 groupSize维度个数的FP16计算并行度
  */
  val numGroups = dimk / groupSize
  val midGroupSize = Design.petileMidGroupSize
  require(dimk % groupSize == 0, s"PETile dimk=$dimk must be divisible by groupSize=$groupSize")
  require(midGroupSize == 4, s"PETile mid-group size is fixed at 4 for scale-aligned ratio exploration, got $midGroupSize")
  val tileAnchorWidth = Design.roundExpWidth
  val numMidGroups = dimk / 16
  val c_unpacker = Module(new CUnpacker)
  val cMantWidth = CUnpackContract.carrierWidth
  // Raw C advances through S01-S09, then decodes at S10/S11.
  // A fixed schedule replaces FIFO state and all in-flight waiting.
  val dotCAddWidth = alignWidth
  require(dotCAddWidth >= cMantWidth, s"CFG_DOT_C_ADD_WIDTH=$dotCAddWidth is too small for C mantissa")
  val midGroupAlignWidth = dotCAddWidth
  val midGroupSumWidth = midGroupAlignWidth + log2Ceil(midGroupSize)
  // MidGroup is the precision-family boundary. Every concrete MidGroup exports
  // the complete Full-reference carrier; family-local width reduction is only
  // legal before this boundary and may only remove positions proven to be zero.
  require(midGroupAlignWidth > 0, s"MidGroup align width must be positive, got $midGroupAlignWidth")
  // midGroupSize is fixed at four, so the default W42 MidGroup result is wider
  // than the W40 C-alignment carrier and defines their common add width.
  val crossAddWidth = midGroupSumWidth
  val topShiftCtrlWidth = log2Ceil(crossAddWidth + 1)
  val mid_group_offsets = (0 until numMidGroups).map(_ * 4)
  val mid_groups: Seq[MidGroupBase] = Seq.fill(numMidGroups)(Module(new MidGroupFull(alignWidth)))

  // Every MidGroup owns its exact LZD/normalization boundary and exports the
  // same atomic {W42 data, corrected anchor, isZero, special} transaction.
  val normalized_mid_results: Seq[ValidIO[MidGroupOutput]] =
    mid_groups.map(_.io.out_mid_data)

  val batch_cfg_q = RegInit(0.U.asTypeOf(new PETileConfig))
  val s_idle :: sAccepting :: sDraining :: Nil = Enum(3)
  val batch_state_q = RegInit(s_idle)

  val cfg_active_mid_mask = VecInit(
    mid_groups.map(_ =>
      PEPrecisionConfigs.fullSupport.supportsDataType(batch_cfg_q.data_type) &&
        PEPrecisionConfigs.fullSupport.supportsDataType(batch_cfg_q.b_data_type)
    )
  )
  val has_active_mid_group = cfg_active_mid_mask.asUInt.orR
  val input_can_flow = batch_state_q === sAccepting
  val ab_input_supported = has_active_mid_group

  val requested_active_mid_mask = VecInit(
    mid_groups.map(_ =>
      PEPrecisionConfigs.fullSupport.supportsDataType(io.in_cfg.bits.data_type) &&
        PEPrecisionConfigs.fullSupport.supportsDataType(io.in_cfg.bits.b_data_type)
    )
  )
  val cfg_request_supported = requested_active_mid_mask.asUInt.orR &&
    PETileMath.legalABPair(io.in_cfg.bits.data_type, io.in_cfg.bits.b_data_type) &&
    PETileMath.legalDataScalePair(io.in_cfg.bits.data_type, io.in_cfg.bits.sf_type) &&
    PETileMath.legalDataScalePair(io.in_cfg.bits.b_data_type, io.in_cfg.bits.b_sf_type) &&
    io.in_cfg.bits.out_type === CDataType.fp32 && io.in_cfg.bits.c_type <= CDataType.bf16 && io.in_cfg.bits.rm <= 4.U

  // Keep ready independent of the offered payload. Unsupported dtype/scale
  // pairs are an interface-contract violation, caught at the handshake, rather
  // than a reason to create a ready-before-valid deadlock.
  io.in_cfg.ready := batch_state_q === s_idle
  io.out_idle := batch_state_q === s_idle

  when(io.in_cfg.fire) {
    assert(cfg_request_supported, "PETile cfg selects no active MidGroup or an illegal dtype/scale pair")
    when(cfg_request_supported) {
      batch_cfg_q := io.in_cfg.bits
      batch_state_q := sAccepting
    }
  }

  // Admission is atomic. Once accepted, no downstream ready can stop AB/C.
  val pair_can_flow = input_can_flow && ab_input_supported
  io.in_ab.ready := pair_can_flow && io.in_c.valid
  io.in_c.ready := pair_can_flow && io.in_ab.valid
  val input_txn_fire = io.in_ab.valid && io.in_c.valid && pair_can_flow

  // The batch cfg remains stable through final result.last, so raw-C stages
  // store only 32 data bits and the per-transaction last/valid bits.
  var previousC = io.in_c.bits.c
  var previousValid = input_txn_fire
  var previousLast = io.in_ab.bits.last
  for (stage <- 1 to PETilePipeline.cRawDelay) {
    val valid_q = RegNext(previousValid, false.B).suggestName(f"s${stage}%02d_c_valid_q")
    val raw_q = RegEnable(previousC, previousValid).suggestName(f"s${stage}%02d_c_raw_q")
    val last_q = RegEnable(previousLast, previousValid).suggestName(f"s${stage}%02d_c_last_q")
    previousC = raw_q
    previousValid = valid_q
    previousLast = last_q
  }
  c_unpacker.io.in_data.valid := previousValid
  c_unpacker.io.in_data.bits.c := previousC
  c_unpacker.io.in_data.bits.c_type := batch_cfg_q.c_type
  c_unpacker.io.in_data.bits.rm := batch_cfg_q.rm
  c_unpacker.io.in_data.bits.out_type := CDataType.fp32
  c_unpacker.io.in_data.bits.last := previousLast

  for (midIdx <- 0 until numMidGroups) {
    val mg = mid_groups(midIdx)
    val mid_group_dimk = mg.midDimk
    val sf_start = mid_group_offsets(midIdx)
    val data_start = sf_start * groupSize
    val g0_start = data_start
    val g1_start = data_start / 2

    mg.io.in_cfg := batch_cfg_q
    mg.io.in_data.bits.a.data := VecInit(io.in_ab.bits.a.data.slice(data_start, data_start + mid_group_dimk))
    mg.io.in_data.bits.a.data_type := batch_cfg_q.data_type
    mg.io.in_data.bits.a.sf.sf_data := VecInit(io.in_ab.bits.a.sf.sf_data.slice(sf_start, sf_start + mg.midNumSF))
    mg.io.in_data.bits.a.sf.sf_type := batch_cfg_q.sf_type
    mg.io.in_data.bits.a.sf.sf_group0 := VecInit(io.in_ab.bits.a.sf.sf_group0.slice(g0_start, g0_start + mid_group_dimk))
    mg.io.in_data.bits.a.sf.sf_group1 := VecInit(io.in_ab.bits.a.sf.sf_group1.slice(g1_start, g1_start + (mid_group_dimk / 2)))

    mg.io.in_data.bits.b.data := VecInit(io.in_ab.bits.b.data.slice(data_start, data_start + mid_group_dimk))
    mg.io.in_data.bits.b.data_type := batch_cfg_q.b_data_type
    mg.io.in_data.bits.b.sf.sf_data := VecInit(io.in_ab.bits.b.sf.sf_data.slice(sf_start, sf_start + mg.midNumSF))
    mg.io.in_data.bits.b.sf.sf_type := batch_cfg_q.b_sf_type
    mg.io.in_data.bits.b.sf.sf_group0 := VecInit(io.in_ab.bits.b.sf.sf_group0.slice(g0_start, g0_start + mid_group_dimk))
    mg.io.in_data.bits.b.sf.sf_group1 := VecInit(io.in_ab.bits.b.sf.sf_group1.slice(g1_start, g1_start + (mid_group_dimk / 2)))

    mg.io.in_data.valid := input_txn_fire && cfg_active_mid_mask(midIdx)
  }
  when(input_txn_fire) {
    assert(io.in_c.fire,
      "PETile AB and C inputs must fire atomically")
    assert(io.in_ab.bits.a.data_type === batch_cfg_q.data_type &&
      io.in_ab.bits.b.data_type === batch_cfg_q.b_data_type,
      "PETile A/B payload data types must match the active batch cfg")
    assert(io.in_ab.bits.a.sf.sf_type === batch_cfg_q.sf_type &&
      io.in_ab.bits.b.sf.sf_type === batch_cfg_q.b_sf_type,
      "PETile A/B payload scale types must match the active batch cfg")
    when(io.in_ab.bits.last) {
      batch_state_q := sDraining
    }
  }

  // S11: every active MidGroup and late-decoded C have identical valid bubbles.
  val c_result = c_unpacker.io.out_data
  val s11_valid = c_result.valid
  for (index <- 0 until numMidGroups) {
    when(cfg_active_mid_mask(index)) {
      assert(normalized_mid_results(index).valid === s11_valid,
        "MidGroup and C must meet at S11 without waiting or backpressure")
    }
  }
  val termCount = numMidGroups + 1
  val inactive_anchor = (-(1 << (tileAnchorWidth - 1))).S(tileAnchorWidth.W)
  val term_magnitudes = Wire(Vec(termCount, UInt((crossAddWidth - 1).W)))
  val term_negatives = Wire(Vec(termCount, Bool()))
  val term_anchors = Wire(Vec(termCount, SInt(tileAnchorWidth.W)))
  val term_active = Wire(Vec(termCount, Bool()))
  for (index <- 0 until numMidGroups) {
    val source = normalized_mid_results(index).bits
    term_active(index) := cfg_active_mid_mask(index) && !source.is_zero
    term_magnitudes(index) := Mux(term_active(index), source.mid_magnitude, 0.U)
    term_negatives(index) := term_active(index) && source.mid_negative
    term_anchors(index) := Mux(term_active(index), source.mid_anchor, inactive_anchor)
  }
  term_active(numMidGroups) := !c_result.bits.is_zero
  // C already carries magnitude + sign, like MidGroup. Append low zeros to
  // match its binary point to the common domain; apply the sign after alignment.
  term_magnitudes(numMidGroups) := Cat(c_result.bits.magnitude, 0.U((crossAddWidth - cMantWidth).W))
  term_negatives(numMidGroups) := c_result.bits.negative
  term_anchors(numMidGroups) := Mux(term_active(numMidGroups), c_result.bits.top_anchor, inactive_anchor)
  val (max_anchor, max_index) = MaxLaneAlign.maximum(term_anchors.toSeq)
  val selected_anchor = Mux(term_active.asUInt.orR, max_anchor, 0.S(tileAnchorWidth.W))
  val shifts = VecInit((0 until termCount).map { index =>
    val delta = (selected_anchor.pad(tileAnchorWidth + 1) -
      term_anchors(index).pad(tileAnchorWidth + 1)).asUInt
    Mux(!term_active(index), 0.U(topShiftCtrlWidth.W),
      Mux(delta >= crossAddWidth.U, crossAddWidth.U(topShiftCtrlWidth.W),
        delta(topShiftCtrlWidth - 1, 0)))
  })
  val special = SpecialValueFlags.mergeAdd((0 until numMidGroups).map { index =>
    Mux(cfg_active_mid_mask(index), normalized_mid_results(index).bits.special,
      0.U.asTypeOf(new SpecialValueFlags))
  } :+ c_result.bits.special)

  // S12: capture terms, winning lane and saturated deltas. C suffix zeros are wiring.
  val s12_valid_q = RegNext(s11_valid, false.B)
  val s12_magnitudes_q = RegEnable(term_magnitudes, s11_valid)
  val s12_negatives_q = RegEnable(term_negatives, s11_valid)
  val s12_shifts_q = RegEnable(shifts, s11_valid)
  val s12_max_index_q = RegEnable(max_index, s11_valid)
  val s12_top_anchor_q = RegEnable(selected_anchor, s11_valid)
  val s12_special_q = RegEnable(special, s11_valid)
  val s12_last_q = RegEnable(c_result.bits.last, s11_valid)

  // S13: all top alignment completes here. No size-dependent result-copy stage.
  val aligned = MaxLaneAlign.fromMagnitudes(
    s12_magnitudes_q.toSeq, s12_negatives_q.toSeq,
    s12_shifts_q.toSeq, s12_max_index_q, crossAddWidth)
  val s13_valid_q = RegNext(s12_valid_q, false.B)
  val s13_terms_q = RegEnable(aligned, s12_valid_q)
  val s13_top_anchor_q = RegEnable(s12_top_anchor_q, s12_valid_q)
  val s13_special_q = RegEnable(s12_special_q, s12_valid_q)
  val s13_last_q = RegEnable(s12_last_q, s12_valid_q)

  // S14: exact balanced sum over all aligned terms, including C.
  val topSumWidth = crossAddWidth + log2Ceil(termCount)
  val sum = s13_terms_q.reduceTree(_ +& _)
  val s14_valid_q = RegNext(s13_valid_q, false.B)
  val s14_sum_q = RegEnable(PETileMath.resizeSInt(sum, topSumWidth), s13_valid_q)
  val s14_top_anchor_q = RegEnable(
    s13_top_anchor_q + (topSumWidth - crossAddWidth).S, s13_valid_q)
  val s14_special_q = RegEnable(s13_special_q, s13_valid_q)
  val s14_last_q = RegEnable(s13_last_q, s13_valid_q)

  // S15/S16: final magnitude/LZD then mantissa extraction with sticky.
  val lzd_normalize = Module(new LzdNormalize(LzdNormalizeConfig(
    inputWidth = topSumWidth, outputMantWidth = Design.roundMantWidth,
    expWidth = tileAnchorWidth)))
  lzd_normalize.io.in_data.valid := s14_valid_q
  lzd_normalize.io.in_data.bits.sum := s14_sum_q
  lzd_normalize.io.in_data.bits.top_anchor := s14_top_anchor_q
  lzd_normalize.io.in_data.bits.rm := batch_cfg_q.rm
  lzd_normalize.io.in_data.bits.out_type := CDataType.fp32
  lzd_normalize.io.in_data.bits.special := s14_special_q
  lzd_normalize.io.in_data.bits.last := s14_last_q

  // S17/S18: FP32-only rounding and packing, always flowing forward.
  val round_pack = Module(new RoundPack(RoundPackConfig(mantWidth = Design.roundMantWidth)))
  round_pack.io.in_data <> lzd_normalize.io.out_data
  io.out_result.valid := round_pack.io.out_data.valid
  io.out_result.bits.result := round_pack.io.out_data.bits.result
  io.out_result.bits.last := round_pack.io.out_data.bits.last
  when(io.out_result.valid && io.out_result.bits.last) {
    assert(batch_state_q === sDraining, "Only a drained final result ends the batch")
    batch_state_q := s_idle
  }
}

/* Global contract: S00 input offer -> S18 FP32 output for every ratio.
 * MidGroup S11: magnitude W41 + sign (W42/S1/I1/F40).
 * C S11: magnitude W24 + sign (W25/S1/I1/F23).
 * S13 common alignment W42/S1/I1/F40; S14 grows by ceil(log2(Nmid+1))
 * and increases topAnchor by the same amount. The final FP32 encoding is
 * sign 1 / exponent 8 / fraction 23, with normal hidden significand bit.
 */
