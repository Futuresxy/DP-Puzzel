package dp.utils

import dp.config._
import chisel3._
import chisel3.util._

object DecodePrimitives {
  //TODO： 待优化，避免每种数据都要实例化一个解包函数。
  def unpackFP16(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(15)
    val exp  = d(14, 10)
    val mant = d(9, 0)
    val is_z  = exp === 0.U
    val is_special = exp.andR
    // 扩展到 E5 同样的宽度或标准处理
    (sign,
      Mux(is_special, 1.U(5.W), Mux(is_z, 1.U(5.W), exp)),
      Mux(is_special, 0.U(12.W), Cat(!is_z, mant, 0.U(1.W))))
  }

  def unpackBF16(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(15)
    val exp  = d(14, 7)
    val mant = d(6, 0)
    val is_z  = exp === 0.U
    val is_special = exp.andR
    (sign,
      Mux(is_special, 1.U(8.W), Mux(is_z, 1.U(8.W), exp)),
      Mux(is_special, 0.U(8.W), Cat(!is_z, mant)))
  }

  // FP8 -> E5M2 Base
  def unpackE5M2(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(7)
    val exp  = d(6, 2)
    val mant = d(1, 0)
    val is_z  = exp === 0.U
    val is_special = exp.andR
    val e_out = Mux(is_special, 1.U(5.W), Mux(is_z, 1.U(5.W), exp))
    (sign, e_out,
      Mux(is_special, 0.U(4.W), Cat(!is_z, mant, 0.U(1.W)))) // 补齐到 4-bit Mantissa
  }

  def unpackE4M3(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(7)
    val exp4 = d(6, 3)
    val mant = d(2, 0)
    val is_z  = exp4 === 0.U
    val is_nan = exp4.andR && mant.andR
    val exp_subnormal = 1.U +& (FPBias.e5Bias - FPBias.e4Bias).U
    val exp_adjusted = exp4 +& (FPBias.e5Bias - FPBias.e4Bias).U
    // OCP MX E4M3 is finite-only apart from the all-ones NaN code.  In
    // particular, exponent 0xf with mantissa 0x0..0x6 is finite and must be
    // rebased normally instead of being promoted to an E5 special exponent.
    // NaN is classified on the sideband and replaced by a finite-safe numeric
    // placeholder; every finite code still uses the ordinary bias translation.
    val e_out = Mux(is_nan, 1.U(5.W), Mux(is_z, exp_subnormal, exp_adjusted))
    (sign, e_out, Mux(is_nan, 0.U(4.W), Cat(!is_z, mant)))
  }

  def classifyFP16(d: UInt): (Bool, Bool, Bool) = {
    val exp = d(14, 10)
    val frac = d(9, 0)
    (exp.andR && frac.orR, exp.andR && !frac.orR, !exp.orR && !frac.orR)
  }

  def classifyBF16(d: UInt): (Bool, Bool, Bool) = {
    val exp = d(14, 7)
    val frac = d(6, 0)
    (exp.andR && frac.orR, exp.andR && !frac.orR, !exp.orR && !frac.orR)
  }

  def classifyE5M2(d: UInt): (Bool, Bool, Bool) = {
    val exp = d(6, 2)
    val frac = d(1, 0)
    (exp.andR && frac.orR, exp.andR && !frac.orR, !exp.orR && !frac.orR)
  }

  def classifyE4M3(d: UInt): (Bool, Bool, Bool) = {
    val magnitude = d(6, 0)
    (magnitude.andR, false.B, !magnitude.orR)
  }

  def classifyE3M2(d: UInt): (Bool, Bool, Bool) =
    (false.B, false.B, !d(4, 0).orR)

  def classifyE2M3(d: UInt): (Bool, Bool, Bool) =
    (false.B, false.B, !d(4, 0).orR)

  // FP6 -> E5 Base (统一到FP8位宽处理)
  def unpackE3M2(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(5)
    val exp3 = d(4, 2)
    val mant = d(1, 0)
    val is_z  = exp3 === 0.U
    val exp_subnormal = 1.U +& (FPBias.e5Bias - FPBias.e3Bias).U
    val exp_adjusted = exp3 +& (FPBias.e5Bias - FPBias.e3Bias).U
    // OCP MXFP6 E3M2 has no Inf/NaN encodings: exponent 0x7 is finite.
    val e_out = Mux(is_z, exp_subnormal, exp_adjusted)
    (sign, e_out, Cat(!is_z, mant, 0.U(1.W)))
  }

  def unpackE2M3(d: UInt): (UInt, UInt, UInt) = {
    val sign = d(5)
    val exp2 = d(4, 3)
    val mant = d(2, 0)
    val is_z  = exp2 === 0.U
    val exp_subnormal = 1.U +& (FPBias.e5Bias - FPBias.e2Bias).U
    val exp_adjusted = exp2 +& (FPBias.e5Bias - FPBias.e2Bias).U
    // OCP MXFP6 E2M3 has no Inf/NaN encodings: exponent 0x3 is finite.
    val e_out = Mux(is_z, exp_subnormal, exp_adjusted)
    (sign, e_out(4,0), Cat(!is_z, mant))
  }

  // FP4 E2M1 解包 - 注意解包后 FP4没有独立的指数位，指数全融合到尾数中，需特殊处理
  //一位小数
  def unpackE2M1(data: UInt): (UInt, UInt) = {
    val sign   = data(3)
    val exp_e2 = data(2, 1)
    val m0     = data(0)
    val e1 = exp_e2(1)
    val e0 = exp_e2(0)
    val mant_o = Cat(
      e1 && e0,
      (e1 && !e0) || (e1 && e0 && m0),
      (!e1 && e0) || (e1 && !e0 && m0),
      !e1 && m0
    )
    (sign, mant_o)
  }
  // S1P2 一位符号位 一位整数 2位小数位，指数全融合到尾数中，实际表示范围为0.25~1.75
  //两位小数
  def unpackHiF4(data: UInt, g0Bit: UInt): (UInt, UInt) = {
    val sign = data(3)
    val mant = Mux(g0Bit.asBool, Cat(data(2, 0), 0.U(1.W)), Cat(0.U(1.W), data(2, 0)))
    (sign, mant)
  }

  // SF Unpack Logic E8M0 E4M3 E6M2
  class SFUnpackResult extends Bundle {
    val exp = UInt(8.W)
    val mant = UInt(4.W)
    val is_nan = Bool()
    val is_inf = Bool()
    val is_zero = Bool()
  }

  def unpackSF(sfData: UInt, sfType: UInt): SFUnpackResult = {
    val res = Wire(new SFUnpackResult)
    val bias_8 = FPBias.e8Bias.U
    val e4_diff = (FPBias.e8Bias - FPBias.e4Bias).U
    val e6_diff = (FPBias.e8Bias - FPBias.e6Bias).U

    // 默认值
    res.exp := FPBias.e8Bias.U
    res.mant := "b1000".U
    res.is_nan := false.B
    res.is_inf := false.B
    res.is_zero := false.B

    switch(sfType) {
      is(MX.e8_m0) { //UE8M0
        val is_nan = sfData.andR
        res.exp := Mux(is_nan, FPBias.e8Bias.U, sfData)
        res.mant := "b1000".U //1.0
        res.is_nan := is_nan
      }
      is(MX.e4_m3) {
        val e4 = sfData(6, 3)
        val m3 = sfData(2, 0)
        val is_z = e4 === 0.U
        val is_nan = e4.andR && m3.andR
        val is_zero = is_z && !m3.orR
        val exp_subnormal_e8 = 1.U +& e4_diff
        // UE4M3 scale codes 0x78..0x7e are finite.  Only 0x7f is NaN; it is
        // classified on the sideband while the maximum finite exponent is
        // translated like every other normal value.
        val exp_e8 = Mux(is_nan, FPBias.e8Bias.U,
          Mux(is_z, exp_subnormal_e8, e4 +& e4_diff))
        res.exp := exp_e8
        res.mant := Mux(is_nan, "b1000".U, Cat(!is_z, m3))
        res.is_nan := is_nan
        res.is_zero := is_zero
      }
      is(MX.e6_m2) {
        val e6 = sfData(7, 2)
        val m2 = sfData(1, 0)
        val is_nan = sfData.andR
        val exp_e8 = e6 +& e6_diff
        res.exp := Mux(is_nan, FPBias.e8Bias.U, exp_e8)
        res.mant := Mux(is_nan, "b1000".U,
          Cat(1.U(1.W), m2, 0.U(1.W))) //恒为1隐藏
        res.is_nan := is_nan
      }
    }
    res
  }
}
