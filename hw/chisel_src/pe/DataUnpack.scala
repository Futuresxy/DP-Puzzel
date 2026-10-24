package dp.pe
import dp.config._
import dp.core.VectorInputBundle
import chisel3._
import chisel3.util._
// -------------------------------------------------------------------
// 核心解包工具对象 (纯函数，易于测试)
// -------------------------------------------------------------------
object UnpackUtils {
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
/*  指数解包输出
  * exp_o 多维度指数
  * scaleexp_o 缩放因子指数
  * type_o 数据类型
 */
class VectorUnpackExpBundle(dimk: Int, expDataWidth: Int, numSF: Int) extends Bundle {
  val pegroup_exp_o      = Vec(dimk, UInt(expDataWidth.W))
  val pegroup_scaleexp_o = Vec(numSF, UInt(8.W))
  val pegroup_type_o    = UInt(DataType.len.W)

}
/*  尾数解包输出
  * mant_o 多维度尾数
  * scalemant_o 缩放因子尾数
  * type_o 数据类型
 */
class VectorUnpackMantBundle(dimk: Int, mantDataWidth: Int, numSF: Int) extends Bundle {
  val pegroup_mant_o      = Vec(dimk, UInt(mantDataWidth.W))
  val pegroup_scalemant_o = Vec(numSF, UInt(4.W))
  val pegroup_type_o      = UInt(DataType.len.W)
}
/*  符号位解包输出*/
class VectorUnpackSignBundle(dimk: Int, signDataWidth: Int) extends Bundle {
  val pegroup_sign_o = Vec(dimk, UInt(signDataWidth.W))
}

/** Per-element operand classification after element and scale are combined. */
class VectorUnpackClassBundle(dimk: Int, classW: Int) extends Bundle {
  val is_nan = Vec(dimk, UInt(classW.W))
  val is_inf = Vec(dimk, UInt(classW.W))
  val is_zero = Vec(dimk, UInt(classW.W))
  val lane_active = Vec(dimk, UInt(classW.W))
}

/*  单向量解包输出接口
  * pegroup_exp_o 指数解包输出
  * pegroup_mant_o 尾数解包输出
  * pegroup_sign_o 符号位解包输出
  * */
class VectorUnpackBundle(dimk: Int, numSF: Int, expW: Int, mantW: Int, signW: Int) extends Bundle {
  val pegroup_exp_o  = new VectorUnpackExpBundle(dimk, expW, numSF)
  val pegroup_mant_o = new VectorUnpackMantBundle(dimk, mantW, numSF)
  val pegroup_sign_o = new VectorUnpackSignBundle(dimk, signW)
  val pegroup_class_o = new VectorUnpackClassBundle(dimk, signW)
}
/*  PEGroupa b向量解包输出接口
  * pegroup_unpack_a  解包输出
  * pegroup_unpack_b  解包输出
  * */
class DataUnpackOutput(
  dimk: Int,
  numSF: Int,
  expW: Int = Design.unpackExpWidth,
  mantW: Int = Design.unpackMantWidth,
  signW: Int = Design.unpackSignWidth
) extends Bundle {
  val pegroup_unpack_a = new VectorUnpackBundle(dimk, numSF, expW, mantW, signW)
  val pegroup_unpack_b = new VectorUnpackBundle(dimk, numSF, expW, mantW, signW)
  // The PEGroup consumes Ti classes only as one canonical additive state.
  // Reduce before the optional unpack output register so lane-local class
  // vectors do not become stored interface state.
  val pegroup_special = new SpecialValueFlags
}

abstract class DataUnpackBase(
  dimk: Int,
  numSF: Int,
  numG0: Int,
  numG1: Int,
  expW: Int = Design.unpackExpWidth,
  mantW: Int = Design.unpackMantWidth,
  signW: Int = Design.unpackSignWidth
) extends Module {
  val io = IO(new Bundle {
    val in_data      = Flipped(Valid(new PEGroupInput(dimk, numSF, numG0, numG1)))
    val out_data = Valid(new DataUnpackOutput(dimk, numSF, expW, mantW, signW))
  })
}

// -------------------------------------------------------------------
// PE Group 数据解包主模块
// -------------------------------------------------------------------
class DataUnpack(
  dimk: Int,
  numSF: Int,
  numG0: Int,
  numG1: Int,
  precisionConfig: PEPrecisionConfig = PEPrecisionConfigs.fullSupport,
  expW: Int = Design.unpackExpWidth,
  mantW: Int = Design.unpackMantWidth,
  signW: Int = Design.unpackSignWidth,
  registeredOutput: Boolean = true,
  compactInputRegister: Boolean = false
) extends DataUnpackBase(dimk, numSF, numG0, numG1, expW, mantW, signW) {
  import UnpackUtils._

  require(!(registeredOutput && compactInputRegister),
    "PEGroup_Dataunpack cannot enable both registeredOutput and compactInputRegister")

  // 1. 编译时断言：当前 PEGroup 只支持每组一个共享缩放因子。
  require(numSF == 1, s"PEGroup_Dataunpack currently supports exactly one scale factor per group, got numSF=$numSF")

  // 2. 编译时断言：确保 HiF4 逻辑的参数关系成立。
  require(numG0 == dimk, s"For HiF4 logic, numG0 ($numG0) must equal dimk ($dimk)")
  require((numG0 % 2) == 0, s"For HiF4 logic, numG0 ($numG0) must be even")
  require(numG1 == (numG0 / 2),
    s"For HiF4 logic, numG1 ($numG1) must equal numG0/2 = ${numG0 / 2}")

  // 3. 参数定义 (确保 Design.xx 是 Scala Int 参数定于是否进对应数据类型的支持)
  val enableFP16 = precisionConfig.supportsFP16 || precisionConfig.supportsBF16
  val enableFP8  = precisionConfig.supportsFP8
  val enableFP6  = precisionConfig.supportsFP6
  val enableFP4  = precisionConfig.supportsFP4
  private val highPrecisionOnly = enableFP16 && !enableFP8 && !enableFP6 && !enableFP4

  def isSupportedDataType(dataType: UInt): Bool = precisionConfig.supportsDataType(dataType)

  def isSupportedSFType(sfType: UInt): Bool = {
    sfType === MX.e8_m0 || sfType === MX.e4_m3 || sfType === MX.e6_m2 ||sfType === MX.none
  }

  def usesSharedScaleFactor(dataType: UInt): Bool = {
    if (highPrecisionOnly) false.B
    else dataType =/= DataType.fp16 && dataType =/= DataType.bf16
  }
  val s01_decoded_q = if (registeredOutput) Some(Reg(new DataUnpackOutput(dimk, numSF, expW, mantW, signW))) else None
  val s01_valid_q = if (registeredOutput) Some(RegInit(false.B)) else None
  val s01_raw_input_q = if (compactInputRegister) Some(Reg(new PEGroupInput(dimk, numSF, numG0, numG1))) else None
  val s01_raw_valid_q = if (compactInputRegister) Some(RegInit(false.B)) else None

  val a_data_type_supported = isSupportedDataType(io.in_data.bits.a.data_type)
  val b_data_type_supported = isSupportedDataType(io.in_data.bits.b.data_type)
  val a_sf_type_supported = isSupportedSFType(io.in_data.bits.a.sf.sf_type)
  val b_sf_type_supported = isSupportedSFType(io.in_data.bits.b.sf.sf_type)
  val input_format_legal =
    a_data_type_supported &&
    b_data_type_supported &&
    a_sf_type_supported  &&
    b_sf_type_supported &&
    FormatCompat.legalABPair(
      io.in_data.bits.a.data_type,
      io.in_data.bits.b.data_type
    ) &&
    FormatCompat.legalDataScalePair(
      io.in_data.bits.a.data_type,
      io.in_data.bits.a.sf.sf_type
    ) &&
    FormatCompat.legalDataScalePair(
      io.in_data.bits.b.data_type,
      io.in_data.bits.b.sf.sf_type
    )
  // Fixed forward-only input stage. Output ready cannot stall decoding.
  val input_ready_base = true.B
  val input_fire = io.in_data.valid && input_ready_base && input_format_legal
  when(io.in_data.valid) {
    assert(input_format_legal, "DataUnpack requires legal A/B and data/scale pairs")
  }

  // -------------------------------------------------------------------
  // 处理逻辑函数
  // -------------------------------------------------------------------
  def processVector(
    in: VectorInputBundle,
    expWidth: Int,
    mantWidth: Int,
    signWidth: Int
  ): (Vec[UInt], Vec[UInt], Vec[UInt], Vec[UInt], Vec[UInt],
      Vec[UInt], Vec[UInt], Vec[UInt], Vec[UInt]) = {

    val sign_vec = Wire(Vec(dimk, UInt(signWidth.W)))
    val exp_vec  = Wire(Vec(dimk, UInt(expWidth.W)))
    val mant_vec = Wire(Vec(dimk, UInt(mantWidth.W)))
    val nan_vec = Wire(Vec(dimk, UInt(signWidth.W)))
    val inf_vec = Wire(Vec(dimk, UInt(signWidth.W)))
    val zero_vec = Wire(Vec(dimk, UInt(signWidth.W)))
    val active_vec = Wire(Vec(dimk, UInt(signWidth.W)))

    val slice_fp16 = in.data
    val slice_fp8  = in.data.map(d => VecInit(d(7, 0), d(15, 8))) // 循环内调用.map会对Vec的2个元素分别解码
    val slice_fp4  = in.data.map(d => VecInit((0 until 4).map(k => d(4 * k + 3, 4 * k))))

    val sf_results = Wire(Vec(numSF, new SFUnpackResult))
    val bypass_shared_sf = !usesSharedScaleFactor(in.data_type) // FP16/BF16 virtual scale = 1.0
    for (k <- 0 until numSF) {
      val decoded_sf = unpackSF(in.sf.sf_data(k), in.sf.sf_type)
      sf_results(k).exp := Mux(bypass_shared_sf, FPBias.e8Bias.U(8.W), decoded_sf.exp)
      sf_results(k).mant := Mux(bypass_shared_sf, "b1000".U(4.W), decoded_sf.mant)
      sf_results(k).is_nan := !bypass_shared_sf && decoded_sf.is_nan
      sf_results(k).is_inf := !bypass_shared_sf && decoded_sf.is_inf
      sf_results(k).is_zero := !bypass_shared_sf && decoded_sf.is_zero
    }

    for (i <- 0 until dimk) {
      // ----------------------------------------------------------
      // MuxLookup 聚合逻辑 - 位宽打包布局说明
      // ----------------------------------------------------------
      // 目标输出位宽: Sign_W, Exp_W, Mant_W (来自 Design 全局配置)
      // 每个 i (0 until dimk) 对应一个 16bit 输入字，不同数据类型的打包方式如下：
      //
      // ┌─────────────┬──────────────┬──────────────┬──────────────┬────────────────────────────────┐
      // │  数据类型   │  符号位宽    │   指数位宽   │   尾数位宽   │          布局说明              │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ FP16        │  1bit        │  5bit        │  12bit       │ 单个数据: S(1) + E(5) +       │
      // │             │              │              │  (含hidden)  │ M(10) + hidden(1) + pad(1)    │
      // │             │              │              │              │ → pad到目标位宽               │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ BF16        │  1bit        │  8bit        │  8bit        │ 单个数据: S(1) + E(8) +       │
      // │             │              │              │  (含hidden)  │ M(7) + hidden(1)              │
      // │             │              │              │              │ → pad到目标位宽               │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ E5M2 (FP8)  │  2bit        │  10bit       │  8bit        │ 2个数据并行: 每个 S(1)+E(5)+  │
      // │             │ [s1|s0]      │ [e1|e0]      │ [m1|m0]      │ M(4), Cat拼接成总宽度         │
      // │             │              │ 5+5=10       │ 4+4=8        │ → m pad到Mant_W               │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ E4M3 (FP8)  │  2bit        │  10bit       │  8bit        │ 2个数据并行: 每个 S(1)+E(5)+  │
      // │             │ [s1|s0]      │ [e1|e0]      │ [m1|m0]      │ M(4), E4→E5 bias调整          │
      // │             │              │ 5+5=10       │ 4+4=8        │ → m pad到Mant_W               │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ E3M2 (FP6)  │  2bit        │  10bit       │  8bit        │ 2个FP6数据 (8bit对齐存储)    │
      // │             │ [s1|s0]      │ [e1|e0]      │ [m1|m0]      │ 每个6bit → S(1)+E(5)+M(4)     │
      // │             │              │ 5+5=10       │ 4+4=8        │ E3→E5 bias调整                │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ E2M3 (FP6)  │  2bit        │  10bit       │  8bit        │ 2个FP6数据 (8bit对齐存储)    │
      // │             │ [s1|s0]      │ [e1|e0]      │ [m1|m0]      │ 每个6bit → S(1)+E(5)+M(4)     │
      // │             │              │ 5+5=10       │ 4+4=8        │ E2→E5 bias调整                │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ E2M1 (FP4)  │  4bit        │  0bit        │  16bit       │ 4个数据并行: 每个 S(1)+M(4)   │
      // │ NVFP4       │ [s3:s2:s1:s0]│  (融合)      │ [m3:m2:m1:m0]│ 指数已融合进尾数 (denorm)    │
      // │             │              │              │ 4+4+4+4=16   │ → 不需要 pad                  │
      // ├─────────────┼──────────────┼──────────────┼──────────────┼────────────────────────────────┤
      // │ HiF4        │  4bit        │  Exp_W       │  16bit       │ 4个数据并行: 每个 S(1)+M(4)   │
      // │             │ [s3:s2:s1:s0]│ (来自SF_G1)  │ [m3:m2:m1:m0]│ 指数来自第二级缩放因子        │
      // │             │              │              │ 4+4+4+4=16   │ e_hif4 = sf_group1(i/2)       │
      // └─────────────┴──────────────┴──────────────┴──────────────┴────────────────────────────────┘
      //
      // 注: .pad() 函数用于零扩展到目标位宽 (高位填0)
      //
      val sign_sel = WireDefault(0.U(signWidth.W))
      val exp_sel = WireDefault(0.U(expWidth.W))
      val mant_sel = WireDefault(0.U(mantWidth.W))
      val element_nan_sel = WireDefault(0.U(signWidth.W))
      val element_inf_sel = WireDefault(0.U(signWidth.W))
      val element_zero_sel = WireDefault(0.U(signWidth.W))

      if(enableFP16) {
        val (s_fp16, e_fp16, m_fp16) = unpackFP16(slice_fp16(i))
        val (s_bf16, e_bf16, m_bf16) = unpackBF16(slice_fp16(i))
        val fp16_class = classifyFP16(slice_fp16(i))
        val bf16_class = classifyBF16(slice_fp16(i))
        when(in.data_type === DataType.fp16) {
          sign_sel := s_fp16
          exp_sel := e_fp16.pad(expWidth)
          mant_sel := m_fp16.pad(mantWidth)
          element_nan_sel := fp16_class._1.asUInt
          element_inf_sel := fp16_class._2.asUInt
          element_zero_sel := fp16_class._3.asUInt
        }.elsewhen(in.data_type === DataType.bf16) {
          sign_sel := s_bf16
          exp_sel := e_bf16.pad(expWidth)
          mant_sel := m_bf16.pad(mantWidth)
          element_nan_sel := bf16_class._1.asUInt
          element_inf_sel := bf16_class._2.asUInt
          element_zero_sel := bf16_class._3.asUInt
        }
      }
      if(enableFP8) {
        val res_e5m2 = slice_fp8(i).map(unpackE5M2)
        val res_e4m3 = slice_fp8(i).map(unpackE4M3)
        val class_e5m2 = slice_fp8(i).map(classifyE5M2)
        val class_e4m3 = slice_fp8(i).map(classifyE4M3)
        val (s_e5, e_e5) = (Cat(res_e5m2.map(_._1).reverse), Cat(res_e5m2.map(_._2).reverse))
        val m_e5 = Cat(res_e5m2(1)._3, 0.U(4.W), res_e5m2(0)._3)
        val (s_e4, e_e4) = (Cat(res_e4m3.map(_._1).reverse), Cat(res_e4m3.map(_._2).reverse))
        val m_e4 = Cat(res_e4m3(1)._3, 0.U(4.W), res_e4m3(0)._3)
        when(in.data_type === DataType.e5_m2) {
          sign_sel := s_e5
          exp_sel := e_e5.pad(expWidth)
          mant_sel := m_e5.pad(mantWidth)
          element_nan_sel := Cat(class_e5m2.map(_._1).reverse)
          element_inf_sel := Cat(class_e5m2.map(_._2).reverse)
          element_zero_sel := Cat(class_e5m2.map(_._3).reverse)
        }.elsewhen(in.data_type === DataType.e4_m3) {
          sign_sel := s_e4
          exp_sel := e_e4.pad(expWidth)
          mant_sel := m_e4.pad(mantWidth)
          element_nan_sel := Cat(class_e4m3.map(_._1).reverse)
          element_inf_sel := Cat(class_e4m3.map(_._2).reverse)
          element_zero_sel := Cat(class_e4m3.map(_._3).reverse)
        }
      }
      if(enableFP6) {
        val res_e3m2 = slice_fp8(i).map(unpackE3M2)
        val res_e2m3 = slice_fp8(i).map(unpackE2M3)
        val class_e3m2 = slice_fp8(i).map(classifyE3M2)
        val class_e2m3 = slice_fp8(i).map(classifyE2M3)
        val (s_e3, e_e3) = (Cat(res_e3m2.map(_._1).reverse), Cat(res_e3m2.map(_._2).reverse))
        val m_e3 = Cat(res_e3m2(1)._3, 0.U(4.W), res_e3m2(0)._3)
        val (s_e2, e_e2) = (Cat(res_e2m3.map(_._1).reverse), Cat(res_e2m3.map(_._2).reverse))
        val m_e2 = Cat(res_e2m3(1)._3, 0.U(4.W), res_e2m3(0)._3)
        when(in.data_type === DataType.e3_m2) {
          sign_sel := s_e3
          exp_sel := e_e3.pad(expWidth)
          mant_sel := m_e3.pad(mantWidth)
          element_nan_sel := Cat(class_e3m2.map(_._1).reverse)
          element_inf_sel := Cat(class_e3m2.map(_._2).reverse)
          element_zero_sel := Cat(class_e3m2.map(_._3).reverse)
        }.elsewhen(in.data_type === DataType.e2_m3) {
          sign_sel := s_e2
          exp_sel := e_e2.pad(expWidth)
          mant_sel := m_e2.pad(mantWidth)
          element_nan_sel := Cat(class_e2m3.map(_._1).reverse)
          element_inf_sel := Cat(class_e2m3.map(_._2).reverse)
          element_zero_sel := Cat(class_e2m3.map(_._3).reverse)
        }
      }
      if(enableFP4) {
        val res_e2m1 = slice_fp4(i).map(unpackE2M1)
        val res_hif4 = slice_fp4(i).map(chunk => unpackHiF4(chunk, in.sf.sf_group0(i)))
        val s_fp4    = Cat(res_e2m1.map(_._1).reverse)
        val m_fp4    = Cat(res_e2m1.map(_._2).reverse)
        val e_fp4    = 0.U(expWidth.W) //mxfp4指数已融合进入尾数
        val s_hif4   = Cat(res_hif4.map(_._1).reverse)
        val m_hif4   = Cat(res_hif4.map(_._2).reverse)
        val e_hif4   = in.sf.sf_group1(i / 2).pad(expWidth)  //此处为第二级缩放因子
        val element_zero_fp4 = Cat(slice_fp4(i).map(d => !d(2, 0).orR).reverse)
        when(in.data_type === DataType.e2_m1 || in.data_type === DataType.nvfp4) {
          sign_sel := s_fp4
          exp_sel := e_fp4
          mant_sel := m_fp4
          element_zero_sel := element_zero_fp4
        }.elsewhen(in.data_type === DataType.hi_f4) {
          sign_sel := s_hif4
          exp_sel := e_hif4
          mant_sel := m_hif4
          element_zero_sel := element_zero_fp4
        }
      }

      val lane_active = if (highPrecisionOnly) 1.U(signWidth.W)
        else FormatCompat.laneMask(in.data_type, signWidth)
      val scale_nan_mask = Fill(signWidth, sf_results(0).is_nan) & lane_active
      val scale_inf_mask = Fill(signWidth, sf_results(0).is_inf) & lane_active
      val scale_zero_mask = Fill(signWidth, sf_results(0).is_zero) & lane_active
      val element_nan = element_nan_sel & lane_active
      val element_inf = element_inf_sel & lane_active
      val element_zero = element_zero_sel & lane_active
      val operand_nan = (
        scale_nan_mask | element_nan |
          (scale_zero_mask & element_inf) |
          (scale_inf_mask & element_zero)
      ) & lane_active
      val operand_inf = (scale_inf_mask | element_inf) & ~operand_nan & lane_active
      val operand_zero = (scale_zero_mask | element_zero) &
        ~operand_nan & ~operand_inf & lane_active

      sign_vec(i) := sign_sel
      exp_vec(i)  := exp_sel
      mant_vec(i) := mant_sel
      nan_vec(i) := operand_nan
      inf_vec(i) := operand_inf
      zero_vec(i) := operand_zero
      active_vec(i) := lane_active
    }

    (sign_vec, exp_vec, mant_vec,
      VecInit(sf_results.map(_.exp)), VecInit(sf_results.map(_.mant)),
      nan_vec, inf_vec, zero_vec, active_vec)
  }

  // -------------------------------------------------------------------
  // 流水线控制
  // -------------------------------------------------------------------
  // 提取全局宽度配置
  val cfgExpW  = expW
  val cfgMantW = mantW
  val cfgSignW = signW

  val decode_input = WireDefault(io.in_data.bits)
  s01_raw_input_q.foreach(decode_input := _)
  val decoded_bits = WireDefault(0.U.asTypeOf(new DataUnpackOutput(dimk, numSF, expW, mantW, signW)))
  val (sa, ea, ma, sfae, sfam, ana, aia, aza, aaa) =
    processVector(decode_input.a, cfgExpW, cfgMantW, cfgSignW)
  val (sb, eb, mb, sfbe, sfbm, anb, aib, azb, aab) =
    processVector(decode_input.b, cfgExpW, cfgMantW, cfgSignW)

  decoded_bits.pegroup_unpack_a.pegroup_sign_o.pegroup_sign_o := sa
  decoded_bits.pegroup_unpack_a.pegroup_exp_o.pegroup_exp_o := ea
  decoded_bits.pegroup_unpack_a.pegroup_exp_o.pegroup_type_o := decode_input.a.data_type
  decoded_bits.pegroup_unpack_a.pegroup_exp_o.pegroup_scaleexp_o := sfae
  decoded_bits.pegroup_unpack_a.pegroup_mant_o.pegroup_mant_o := ma
  decoded_bits.pegroup_unpack_a.pegroup_mant_o.pegroup_scalemant_o := sfam
  decoded_bits.pegroup_unpack_a.pegroup_mant_o.pegroup_type_o := decode_input.a.data_type
  decoded_bits.pegroup_unpack_a.pegroup_class_o.is_nan := ana
  decoded_bits.pegroup_unpack_a.pegroup_class_o.is_inf := aia
  decoded_bits.pegroup_unpack_a.pegroup_class_o.is_zero := aza
  decoded_bits.pegroup_unpack_a.pegroup_class_o.lane_active := aaa

  decoded_bits.pegroup_unpack_b.pegroup_sign_o.pegroup_sign_o := sb
  decoded_bits.pegroup_unpack_b.pegroup_exp_o.pegroup_exp_o := eb
  decoded_bits.pegroup_unpack_b.pegroup_exp_o.pegroup_type_o := decode_input.b.data_type
  decoded_bits.pegroup_unpack_b.pegroup_exp_o.pegroup_scaleexp_o := sfbe
  decoded_bits.pegroup_unpack_b.pegroup_mant_o.pegroup_mant_o := mb
  decoded_bits.pegroup_unpack_b.pegroup_mant_o.pegroup_scalemant_o := sfbm
  decoded_bits.pegroup_unpack_b.pegroup_mant_o.pegroup_type_o := decode_input.b.data_type
  decoded_bits.pegroup_unpack_b.pegroup_class_o.is_nan := anb
  decoded_bits.pegroup_unpack_b.pegroup_class_o.is_inf := aib
  decoded_bits.pegroup_unpack_b.pegroup_class_o.is_zero := azb
  decoded_bits.pegroup_unpack_b.pegroup_class_o.lane_active := aab

  val ti_nan_by_word = Wire(Vec(dimk, UInt(cfgSignW.W)))
  val ti_pos_inf_by_word = Wire(Vec(dimk, UInt(cfgSignW.W)))
  val ti_neg_inf_by_word = Wire(Vec(dimk, UInt(cfgSignW.W)))
  for (i <- 0 until dimk) {
    val lane_active = aaa(i) & aab(i)
    val ti_nan = (
      ana(i) | anb(i) |
        (aia(i) & azb(i)) |
        (aza(i) & aib(i))
    ) & lane_active
    val ti_inf = (aia(i) | aib(i)) & ~ti_nan & lane_active
    val ti_sign = (sa(i) ^ sb(i)) & lane_active

    ti_nan_by_word(i) := ti_nan
    ti_pos_inf_by_word(i) := ti_inf & ~ti_sign
    ti_neg_inf_by_word(i) := ti_inf & ti_sign
  }
  decoded_bits.pegroup_special := SpecialValueFlags.fromSeen(
    ti_nan_by_word.asUInt.orR,
    ti_pos_inf_by_word.asUInt.orR,
    ti_neg_inf_by_word.asUInt.orR
  )

  if (registeredOutput) {
    val out = s01_decoded_q.get
    val valid = s01_valid_q.get
    when(input_fire) {
      out := decoded_bits
      valid := true.B
    }.otherwise {
      valid := false.B
    }
    io.out_data.bits := out
    io.out_data.valid := valid
  } else if (compactInputRegister) {
    val compact = s01_raw_input_q.get
    val valid = s01_raw_valid_q.get
    when(input_ready_base) {
      valid := io.in_data.valid && input_format_legal
    }
    when(input_fire) {
      compact := io.in_data.bits
    }
    io.out_data.bits := decoded_bits
    io.out_data.valid := valid
  } else {
    io.out_data.bits := decoded_bits
    io.out_data.valid := io.in_data.valid && input_format_legal
  }
  // Ready only rejects illegal input formats; it never pauses accepted data.
}
