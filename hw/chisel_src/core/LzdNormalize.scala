package dp.core

import chisel3._
import chisel3.util._
import dp.config._
import dp.common.BalancedLeadingZero

// =================================================================
// 配置类
// =================================================================
case class LzdNormalizeConfig(
  inputWidth: Int = Design.dotCAddWidth + 2 + log2Ceil(Resource.dimK / 16 + 1),      // 输入累加结果位宽
  outputMantWidth: Int = Design.roundMantWidth, // 输出尾数位宽 [hidden][frac][round][sticky...]
  expWidth: Int = Design.lzdExpWidth
) {
  require(inputWidth > 0, "Input width must be positive")
  require(outputMantWidth > 0, "Output mantissa width must be positive")
  require(expWidth > 0, "Exponent width must be positive")
}

// =================================================================
// 输入接口
// =================================================================
class LzdNormalizeInput(cfg: LzdNormalizeConfig) extends Bundle {
  val sum        = SInt(cfg.inputWidth.W)  // 累加结果
  val top_anchor  = SInt(cfg.expWidth.W)    // sum 最高 magnitude bit 对应的指数
  val rm         = UInt(3.W)               // 舍入模式
  val out_type    = UInt(3.W)               // 输出类型
  val special    = new SpecialValueFlags
  val last       = Bool()                  // 当前 batch 的最后一个事务
}

// =================================================================
// 输出接口
// =================================================================
class LzdNormalizeOutput(cfg: LzdNormalizeConfig) extends Bundle {
  val sign       = Bool()                       // 符号位
  val exp        = SInt(cfg.expWidth.W)         // 去偏移的指数
  val mant       = UInt(cfg.outputMantWidth.W)  // 规格化尾数 [1.xxx..RoundSticky]
  val is_zero    = Bool()                       // 零标志
  val rm         = UInt(3.W)                    // 透传舍入模式
  val out_type    = UInt(3.W)                    // 透传输出类型
  val special    = new SpecialValueFlags
  val last       = Bool()                       // 透传 batch 结束标记
}

// =================================================================
// 前导0检测器（独立模块）
// =================================================================
// =================================================================
// LZD与规格化主模块
// =================================================================
/**
 * 前导0检测与规格化模块
 * 功能：
 * 1. 对有符号累加结果取绝对值
 * 2. 执行前导0检测（LZD）
 * 3. 规格化左移至 1.xxxx 格式
 * 4. 提取指定位宽的尾数（包含round和sticky位）
 * 5. 计算规格化后的指数
 */
class LzdNormalize(cfg: LzdNormalizeConfig = LzdNormalizeConfig()) extends Module {
  val io = IO(new Bundle {
    val in_data = Flipped(Valid(new LzdNormalizeInput(cfg)))
    val out_data = Valid(new LzdNormalizeOutput(cfg))
  })

  // =================================================================
  // 流水线寄存器
  // =================================================================
  val s15_valid_q = RegNext(io.in_data.valid, false.B)
  val s15_sign_q = Reg(Bool())
  val s15_lead_zeros_q = Reg(UInt(log2Ceil(cfg.inputWidth + 1).W))
  val s15_is_zero_q = Reg(Bool())
  val s15_top_anchor_q = Reg(SInt(cfg.expWidth.W))
  val s15_rm_q = Reg(UInt(3.W))
  val s15_out_type_q = Reg(UInt(3.W))
  val s15_special_q = Reg(new SpecialValueFlags)
  val s15_last_q = Reg(Bool())
  val s16_result_q   = Reg(new LzdNormalizeOutput(cfg))
  val s16_valid_q = RegNext(s15_valid_q, false.B)
  val lzd = Module(new LeadingZeroCounter(cfg.inputWidth))

  // 握手逻辑
  io.out_data.valid := s16_valid_q
  io.out_data.bits := s16_result_q

  // =================================================================
  // 主逻辑
  // =================================================================
  val sum_in = io.in_data.bits.sum
  val sign_bit = sum_in < 0.S
  val abs_val = Mux(sign_bit, -sum_in, sum_in).asUInt
  val s15_abs_q = Reg(UInt(abs_val.getWidth.W))
  val is_zero = abs_val === 0.U
  lzd.io.in_data := abs_val
  val lead_zeros = lzd.io.out_count
  val s15_fire = s15_valid_q

  when(io.in_data.valid) {
    s15_sign_q := sign_bit
    s15_abs_q := abs_val
    s15_lead_zeros_q := lead_zeros
    s15_is_zero_q := is_zero
    s15_top_anchor_q := io.in_data.bits.top_anchor
    s15_rm_q := io.in_data.bits.rm
    s15_out_type_q := io.in_data.bits.out_type
    s15_special_q := io.in_data.bits.special
    s15_last_q := io.in_data.bits.last
  }

  val norm_full = (s15_abs_q << s15_lead_zeros_q).asUInt
  val leading_one_pos = (cfg.inputWidth - 1).U(s15_lead_zeros_q.getWidth.W) - s15_lead_zeros_q
  val mant_extracted = Wire(UInt(cfg.outputMantWidth.W))

  if (cfg.inputWidth > cfg.outputMantWidth) {
    val upper_bits = norm_full(cfg.inputWidth - 1, cfg.inputWidth - cfg.outputMantWidth + 1)
    val lower_bits = norm_full(cfg.inputWidth - cfg.outputMantWidth, 0)
    mant_extracted := Cat(upper_bits, lower_bits.orR)
  } else if (cfg.inputWidth == cfg.outputMantWidth) {
    mant_extracted := norm_full
  } else {
    mant_extracted := Cat(norm_full, 0.U((cfg.outputMantWidth - cfg.inputWidth).W))
  }

  val exp_base = s15_top_anchor_q - (cfg.inputWidth - 2).S(cfg.expWidth.W)
  val exp_normalized = exp_base +& leading_one_pos.zext

  when(s15_fire) {
    s16_result_q.sign := s15_sign_q
    s16_result_q.exp := Mux(s15_is_zero_q, 0.S(cfg.expWidth.W), exp_normalized)
    s16_result_q.mant := Mux(s15_is_zero_q, 0.U, mant_extracted)
    s16_result_q.is_zero := s15_is_zero_q
    s16_result_q.rm := s15_rm_q
    s16_result_q.out_type := s15_out_type_q
    s16_result_q.special := s15_special_q
    s16_result_q.last := s15_last_q

  }
}
