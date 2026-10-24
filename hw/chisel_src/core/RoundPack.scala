package dp.core

import chisel3._
import chisel3.util._
import dp.config._

// =================================================================
// 舍入与打包模块
// =================================================================

/**
 * 舍入与打包输入接口
 */
class RoundPackInput(val mantWidth: Int) extends Bundle {
  val sign       = Bool()      // 符号位
  val exp        = SInt(Design.roundExpWidth.W)  // 去偏移的指数
  val mant       = UInt(mantWidth.W)  // 规格化尾数 [1.frac...RoundSticky]
  val is_zero    = Bool()      // 零标志
  val rm         = UInt(3.W)   // 舍入模式
  val out_type = UInt(3.W) // Only FP32=0 is legal.
  val special    = new SpecialValueFlags
  val last       = Bool()      // 当前 batch 的最后一个事务
}

/**
 * 舍入与打包输出接口
 */
class RoundPackOutput extends Bundle {
  val result = UInt(32.W)  // FP32 packed result
  val out_type = UInt(3.W)
  val last = Bool()
}

case class RoundPackConfig(
  mantWidth: Int = Design.roundMantWidth
)

/** S17/S18 fixed-latency FP32 round/pack. No backpressure or optional pipe. */
class RoundPack(cfg: RoundPackConfig = RoundPackConfig()) extends Module {
  require(cfg.mantWidth >= 26)
  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new RoundPackInput(cfg.mantWidth)))
    val out_data = Valid(new RoundPackOutput)
  })
  val stage_bits = io.in_data.bits
  when(io.in_data.valid) { assert(stage_bits.out_type === CDataType.fp32,
    "RoundPack supports only FP32 output") }
  val s17_valid_q = RegNext(io.in_data.valid, false.B)
  val s18_valid_q = RegNext(s17_valid_q, false.B)

  val rounder = Module(new RoundIncrement(23))
  rounder.io.in_fraction := stage_bits.mant(cfg.mantWidth - 2, cfg.mantWidth - 24)
  rounder.io.in_round := stage_bits.mant(cfg.mantWidth - 25)
  rounder.io.in_sticky := stage_bits.mant(cfg.mantWidth - 26, 0).orR
  rounder.io.in_sign := stage_bits.sign
  rounder.io.in_rm := stage_bits.rm
  val expCalcWidth = Design.roundExpWidth + 3
  val exp_biased = stage_bits.exp.pad(expCalcWidth) +& FPBias.fp32Bias.S(expCalcWidth.W)
  val exp_rounded = exp_biased +& rounder.io.out_carry.asUInt.zext
  val is_underflow = exp_biased < 1.S
  val is_overflow = exp_rounded >= FPMAX.e8Max.S
  val rmin = RoundIncrement.roundsToFinite(stage_bits.rm, stage_bits.sign)

  private def shiftedRoundInputs(value: UInt, shift: UInt, outWidth: Int): (UInt, Bool, Bool) = {
    val valueWidth = value.getWidth
    val shiftSelWidth = math.max(1, log2Ceil(valueWidth + 1))
    val compareWidth = math.max(shift.getWidth, shiftSelWidth)
    val shift_wide = shift.pad(compareWidth)
    val max_shift = valueWidth.U(compareWidth.W)
    val over_shift = shift_wide > max_shift
    val capped_shift_wide = Mux(over_shift, max_shift, shift_wide)
    val capped_shift = capped_shift_wide(shiftSelWidth - 1, 0)

    val shifted = MuxLookup(capped_shift, 0.U(outWidth.W))(
      (0 to valueWidth).map { sh =>
        val bits =
          if (sh >= valueWidth) {
            0.U(outWidth.W)
          } else {
            val available = valueWidth - sh
            if (available >= outWidth) {
              value(sh + outWidth - 1, sh)
            } else {
              Cat(0.U((outWidth - available).W), value(valueWidth - 1, sh))
            }
          }
        sh.U(shiftSelWidth.W) -> bits
      }
    )
    val round_bit = MuxLookup(capped_shift, false.B)(
      (0 to valueWidth).map { sh =>
        val bit = if (sh == 0) false.B else value(sh - 1)
        sh.U(shiftSelWidth.W) -> bit
      }
    )
    val sticky_bit_before_over = MuxLookup(capped_shift, false.B)(
      (0 to valueWidth).map { sh =>
        val bit = if (sh <= 1) false.B else value(sh - 2, 0).orR
        sh.U(shiftSelWidth.W) -> bit
      }
    )
    val sticky_bit = Mux(over_shift, value.orR, sticky_bit_before_over)
    // Beyond the full mantissa, every retained/round bit is zero. The operand
    // contributes only sticky; retaining its top bit as round would turn tiny
    // RNE results into a spurious minimum subnormal.
    (shifted, !over_shift && round_bit, sticky_bit)
  }

  private def subnormalShift(fracBits: Int): UInt = {
    val base_shift = (cfg.mantWidth - 1 - fracBits).S
    val denorm_shift = 1.S - exp_biased
    Mux(is_underflow, (base_shift + denorm_shift).asUInt, 0.U)
  }


  val (sub_in, sub_round, sub_sticky) = shiftedRoundInputs(stage_bits.mant, subnormalShift(23), 23)
  val sub_rounder = Module(new RoundIncrement(23))
  sub_rounder.io.in_fraction := sub_in
  sub_rounder.io.in_round := sub_round
  sub_rounder.io.in_sticky := sub_sticky
  sub_rounder.io.in_sign := stage_bits.sign
  sub_rounder.io.in_rm := stage_bits.rm

  val s17_sign_q = RegEnable(stage_bits.sign, io.in_data.valid)
  val s17_zero_q = RegEnable(stage_bits.is_zero, io.in_data.valid)
  val s17_special_q = RegEnable(stage_bits.special, io.in_data.valid)
  val s17_last_q = RegEnable(stage_bits.last, io.in_data.valid)
  val s17_exponent_q = RegEnable(exp_rounded, io.in_data.valid)
  val s17_underflow_q = RegEnable(is_underflow, io.in_data.valid)
  val s17_overflow_q = RegEnable(is_overflow, io.in_data.valid)
  val s17_rmin_q = RegEnable(rmin, io.in_data.valid)
  val s17_fraction_q = RegEnable(rounder.io.out_fraction, io.in_data.valid)
  val s17_sub_fraction_q = RegEnable(sub_rounder.io.out_fraction, io.in_data.valid)
  val s17_sub_carry_q = RegEnable(sub_rounder.io.out_carry, io.in_data.valid)

  val overflow = Cat(s17_sign_q,
    Mux(s17_rmin_q, 254.U(8.W), 255.U(8.W)),
    Mux(s17_rmin_q, Fill(23, 1.U(1.W)), 0.U(23.W)))
  val normal = Cat(s17_sign_q, s17_exponent_q(7, 0).asUInt, s17_fraction_q)
  val subnormal = Cat(s17_sign_q,
    Mux(s17_sub_carry_q, 1.U(8.W), 0.U(8.W)),
    Mux(s17_sub_carry_q, 0.U(23.W), s17_sub_fraction_q))
  val finite_result = Mux(s17_overflow_q, overflow, Mux(s17_underflow_q, subnormal, normal))
  val packed = MuxCase(finite_result, Seq(
    s17_special_q.is_nan -> "h7fc00000".U(32.W),
    s17_special_q.is_pos_inf -> "h7f800000".U(32.W),
    s17_special_q.is_neg_inf -> "hff800000".U(32.W),
    s17_zero_q -> Cat(s17_sign_q, 0.U(31.W))))
  val s18_result_q = RegEnable(packed, s17_valid_q)
  val s18_last_q = RegEnable(s17_last_q, s17_valid_q)
  io.out_data.valid := s18_valid_q
  io.out_data.bits.result := s18_result_q
  io.out_data.bits.last := s18_last_q
  io.out_data.bits.out_type := CDataType.fp32
}

/* Only FP32 output is generated: sign=1, exponent=8, stored fraction=23.
 * Input mantissa contains hidden+23 fraction+round+sticky (at least 26 bits).
 * Rounding and special-value behavior are unchanged; two clocks, no stalls.
 */
