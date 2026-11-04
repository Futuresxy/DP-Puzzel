package dp.pe.e

import dp.config._
import dp.utils._
import dp.utils.DecodePrimitives._
import chisel3._
import chisel3.util._

/** E-only unpack pipeline, S01 output, II=1; Valid-only, reset clears valid.
  * Element/scale semantics and packing are preserved from the source migration.
  */
class DataUnpack_E(
  dimk: Int, numSF: Int, numG0: Int, numG1: Int,
  expW: Int, mantW: Int, signW: Int
) extends DataUnpackBase(dimk, numSF, numG0, numG1, expW, mantW, signW) {
  private val registeredOutput = false
  private val compactInputRegister = true
  private val precisionConfig = Precision.e
  require(registeredOutput == false && compactInputRegister == true, "Dedicated unpack pipeline is fixed")
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
  private val highPrecisionOnly = false

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
      val sign_sel = WireDefault(0.U(signWidth.W))
      val exp_sel = WireDefault(0.U(expWidth.W))
      val mant_sel = WireDefault(0.U(mantWidth.W))
      val element_nan_sel = WireDefault(0.U(signWidth.W))
      val element_inf_sel = WireDefault(0.U(signWidth.W))
      val element_zero_sel = WireDefault(0.U(signWidth.W))





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
