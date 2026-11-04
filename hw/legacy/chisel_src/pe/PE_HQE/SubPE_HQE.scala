package dp.pe.hqe

import chisel3._
import chisel3.util._
import dp.config._
import dp.utils._

/** One decoded packed word reuses four partial-product multipliers across
  * H1/Q2/E4 modes. Valid-only II=1, result latency 3 and early anchor latency 1.
  * Reset clears valid; payload registers hold on bubbles without reset.
  * Q MIN alignment truncates toward zero; other output placement is exact.
  */
class SubPE_HQE(alignment: AlignmentConfig = AlignmentConfig()) extends SubPEBase(SubPEConfig.forFamily("HQE", alignment)) {
  override def desiredName: String = "SubPE_HQE" + alignment.suffix
  cfg.requireInputWidths(exp = 10, mant = 16, sign = 4, anchor = 9)
  when(io.in_data.valid) {
    assert(Precision.hqe.supportsDataType(io.in_data.bits.ab_type),
      "SubPE requires a supported canonical product format")
  }

  // PETile S02-S04: three fixed registers after the S01 unpack output.
  // Valid-only internal ports advance every accepted arithmetic transaction.
  val s02_valid_q = RegNext(io.in_data.valid, false.B)
  val s03_valid_q = RegNext(s02_valid_q, false.B)
  val s04_valid_q = RegNext(s03_valid_q, false.B)
  val s01_fire = io.in_data.valid
  val s02_fire = s02_valid_q
  val s03_fire = s03_valid_q

  // ==============================================================================
  // S01 -> S02: 乘法与提前 anchor
  // ==============================================================================
  val in_data = io.in_data.bits
  // 1.1 数据解包
  val exp_a  = in_data.a_exp
  val exp_b = in_data.b_exp
  val mant_a = in_data.a_mant
  val mant_b = in_data.b_mant
  val sign_a = in_data.a_sign
  val sign_b = in_data.b_sign

  val exp8_a_hi = exp_a(9, 5)
  val exp8_a_lo = exp_a(4, 0)
  val exp8_b_hi = exp_b(9, 5)
  val exp8_b_lo = exp_b(4, 0)

  val ma_16_h = mant_a(11, 4)
  val ma_16_l = mant_a(3, 0)
  val mb_16_h = mant_b(11, 4)
  val mb_16_l = mant_b(3, 0)
  val ma_bf16 = mant_a(7, 0)
  val mb_bf16 = mant_b(7, 0)
  val ma_8_l  = mant_a(3, 0)
  val ma_8_h  = mant_a(11, 8)
  val mb_8_l  = mant_b(3, 0)
  val mb_8_h  = mant_b(11, 8)
  val ma_4 = VecInit((0 until 4).map(i => mant_a(i*4+3, i*4)))
  val mb_4 = VecInit((0 until 4).map(i => mant_b(i*4+3, i*4)))

  // 1.2 格式分类与指数加法。Full SubPE 固定支持全部格式，无需静态 capability 分支。
  def isFP8Family(dataType: UInt): Bool =
    dataType === DataType.e5_m2 || dataType === DataType.e4_m3 ||
      dataType === DataType.e2_m3 || dataType === DataType.e3_m2

  def isHighPrecision(dataType: UInt): Bool =
    dataType === DataType.fp16 || dataType === DataType.bf16

  val s01_is_fp8 = isFP8Family(in_data.ab_type)
  val s01_is_bf16 = in_data.ab_type === DataType.bf16

  // 8-bit adder is shared by BF16 and the low FP8/FP4 exponent lane.
  val adder8_in_a = Mux(s01_is_bf16, exp_a(7, 0), exp8_a_lo)
  val adder8_in_b = Mux(s01_is_bf16, exp_b(7, 0), exp8_b_lo)
  val adder5_in_a = exp8_a_hi
  val adder5_in_b = exp8_b_hi

  val sum_8_res = adder8_in_a +& adder8_in_b
  val sum_5_res = adder5_in_a +& adder5_in_b

  // 1.3 指数分发
  val fp8_hi_is_max = Wire(Bool())
  fp8_hi_is_max := false.B
  val fp8_align_shift = Wire(UInt(6.W))
  fp8_align_shift := 0.U
  val s01_anchor   = Wire(UInt(cfg.subpeAnchorWidth.W))
  s01_anchor := 0.U

  when(s01_is_fp8) {
    val sum_lo = SubPEProductAnchor(sum_8_res(5, 0), ma_8_l, mb_8_l)
    val sum_hi = SubPEProductAnchor(sum_5_res(5, 0), ma_8_h, mb_8_h)
    val hi_is_max = sum_hi > sum_lo
    val max_exp = Mux(hi_is_max, sum_hi, sum_lo)
    val min_exp = Mux(hi_is_max, sum_lo, sum_hi)
    fp8_hi_is_max := hi_is_max
    fp8_align_shift := max_exp - min_exp
    s01_anchor   := max_exp
  }.elsewhen(isHighPrecision(in_data.ab_type)) {
    val a_mant = Mux(s01_is_bf16, ma_bf16.pad(11), mant_a(11, 1))
    val b_mant = Mux(s01_is_bf16, mb_bf16.pad(11), mant_b(11, 1))
    s01_anchor := SubPEProductAnchor(sum_8_res, a_mant, b_mant)
  }.otherwise {
    s01_anchor := sum_8_res
  }

  // 1.4 乘法器路由
  val op0_a = Wire(UInt(4.W))
  val op0_b = Wire(UInt(4.W))
  val op1_a = Wire(UInt(4.W))
  val op1_b = Wire(UInt(8.W))
  val op2_a = Wire(UInt(8.W))
  val op2_b = Wire(UInt(4.W))
  val op3_a = Wire(UInt(8.W))
  val op3_b = Wire(UInt(8.W))

  op0_a := 0.U
  op0_b := 0.U
  op1_a := 0.U
  op1_b := 0.U
  op2_a := 0.U
  op2_b := 0.U
  op3_a := 0.U
  op3_b := 0.U

  when(in_data.ab_type === DataType.fp16) {
    op0_a := ma_16_l
    op0_b := mb_16_l
    op1_a := ma_16_l
    op1_b := mb_16_h
    op2_a := ma_16_h
    op2_b := mb_16_l
    op3_a := ma_16_h
    op3_b := mb_16_h
  }
  when(in_data.ab_type === DataType.bf16) {
    op3_a := ma_bf16
    op3_b := mb_bf16
  }
  when(s01_is_fp8) {
    op0_a := ma_8_l
    op0_b := mb_8_l
    op1_a := ma_8_h
    op1_b := mb_8_h
  }
  when(!isHighPrecision(in_data.ab_type) && !s01_is_fp8) {
    op0_a := ma_4(0)
    op0_b := mb_4(0)
    op1_a := ma_4(1)
    op1_b := mb_4(1)
    op2_a := ma_4(2)
    op2_b := mb_4(2)
    op3_a := ma_4(3)
    op3_b := mb_4(3)
  }

  val mul_res_0 = Wire(UInt(8.W))
  mul_res_0 := op0_a * op0_b
  val mul_res_1 = Wire(UInt(12.W))
  mul_res_1 := op1_a * op1_b
  val mul_res_2 = Wire(UInt(12.W))
  mul_res_2 := op2_a * op2_b
  val mul_res_3 = Wire(UInt(16.W))
  mul_res_3 := op3_a * op3_b

  // 1.5 符号异或
  val sign_xor = Wire(Vec(4, Bool()))
  for(i <- 0 until 4) sign_xor(i) := sign_a(i) ^ sign_b(i)

  // Pipeline Reg 1 -> 2
  val s02_type_q     = RegEnable(in_data.ab_type, s01_fire)
  val s02_mul_0_q    = RegEnable(mul_res_0, s01_fire)
  val s02_mul_1_q    = RegEnable(mul_res_1, s01_fire)
  val s02_mul_2_q    = RegEnable(mul_res_2, s01_fire)
  val s02_mul_3_q    = RegEnable(mul_res_3, s01_fire)
  val s02_sign_q     = RegEnable(sign_xor, s01_fire)
  val s02_fp8_hi_is_max_q = RegEnable(fp8_hi_is_max, s01_fire)
  val s02_fp8_align_shift_q = RegEnable(fp8_align_shift, s01_fire)
  val s02_anchor_q   = RegEnable(s01_anchor, s01_fire)

  // ==============================================================================
  // S02 -> S03: 准备对齐与求和操作数
  // ==============================================================================
  io.out_anchor.valid := s02_valid_q
  io.out_anchor.bits.subpe_anchor := s02_anchor_q  // 无符号原始指数和；高精度/FP8/FP6 零乘积已屏蔽

  private def signedProduct(raw: UInt, negative: Bool): SInt = {
    val magnitude = raw(7, 0).zext
    Mux(negative, -magnitude, magnitude)
  }

  private def resizeSInt(value: SInt, width: Int): SInt = {
    val out = Wire(SInt(width.W))
    if (value.getWidth > width) {
      out := value.asUInt(width - 1, 0).asSInt
    } else {
      out := value.pad(width)
    }
    out
  }

  private def alignTowardZero(value: SInt, lsbZeros: Int, shift: UInt, outWidth: Int): SInt = {
    val extended = if (lsbZeros > 0) Cat(value.asUInt, 0.U(lsbZeros.W)).asSInt else value
    SignedShift.rightTowardZeroToWidth(extended, shift, outWidth)
  }

  private def shiftByConstant(value: SInt, shift: Int, width: Int): SInt = {
    if (shift > 0) resizeSInt(value << shift, width)
    else if (shift < 0) SignedShift.rightTowardZeroToWidth(value, (-shift).U, width)
    else resizeSInt(value, width)
  }

  private val fp4PairSumWidth = 10
  private val fp4FinalSumWidth = fp4PairSumWidth + 1
  private val fp8FinalSumWidth = cfg.fp8RetainWidth + 1
  private val pathAOperandWidth = cfg.outWidth - 1
  private val fp8OutputLsbZeros = cfg.outWidth - fp8FinalSumWidth
  private val fp4OutputLsbZeros = cfg.outWidth - fp4FinalSumWidth

  // Full SubPE never discards local results at its output boundary.
  require(fp8OutputLsbZeros >= 0,
    s"Full SubPE outWidth=${cfg.outWidth} must hold the $fp8FinalSumWidth-bit FP8/FP6 sum")
  require(fp4OutputLsbZeros >= 0,
    s"Full SubPE outWidth=${cfg.outWidth} must hold the $fp4FinalSumWidth-bit FP4 sum")
  require(cfg.outWidth >= cfg.highPrecisionResultWidth,
    s"Full SubPE outWidth=${cfg.outWidth} must hold the ${cfg.highPrecisionResultWidth}-bit FP16/BF16 product")

  /** Place a signed local result at the SubPE output binary point without losing bits. */
  private def placeAtOutput(value: SInt, lsbZeros: Int): SInt = {
    require(value.getWidth + lsbZeros == pathAOperandWidth,
      s"${value.getWidth}-bit operand plus $lsbZeros zeros must fill $pathAOperandWidth bits")
    if (lsbZeros > 0) Cat(value.asUInt, 0.U(lsbZeros.W)).asSInt else value
  }

  private def exportHighPrecisionResult(magnitude: UInt, sign: Bool): SInt = {
    val positive = Cat(0.U(1.W), magnitude).asSInt
    val signed = Mux(sign, -positive, positive)
    shiftByConstant(signed, cfg.outWidth - cfg.highPrecisionResultWidth, cfg.outWidth)
  }

  private def resizeUInt(value: UInt, width: Int): UInt = {
    val out = Wire(UInt(width.W))
    if (value.getWidth > width) {
      out := value(width - 1, 0)
    } else if (value.getWidth < width) {
      out := value.pad(width)
    } else {
      out := value
    }
    out
  }

  // --- Path A: FP8/FP4 ---
  val path_a_ops = Wire(Vec(4, SInt(cfg.fp8ProductSignedWidth.W)))
  path_a_ops(0) := signedProduct(s02_mul_0_q, s02_sign_q(0))
  path_a_ops(1) := signedProduct(s02_mul_1_q, s02_sign_q(1))
  path_a_ops(2) := signedProduct(s02_mul_2_q, s02_sign_q(2))
  path_a_ops(3) := signedProduct(s02_mul_3_q, s02_sign_q(3))

  private val fp8GuardBits = cfg.fp8RetainWidth - cfg.fp8ProductSignedWidth
  // Exactly one FP8/FP6 lane owns the maximum product anchor. Keep that lane
  // in the retained alignment domain by wiring alone and send only the smaller
  // lane through the dynamic signed-RTZ shifter. Equal anchors deterministically
  // select the low lane as MAX; the high lane then traverses the sole shifter
  // with shift zero, which is bit-identical to the former two-shifter path.
  // Keep MAX as its signed product width across S02->S03; its guard suffix is
  // statically zero and is reconstructed by wiring immediately before the CPA.
  val fp8_max_product = Mux(s02_fp8_hi_is_max_q, path_a_ops(1), path_a_ops(0))
  val fp8_min_product = Mux(s02_fp8_hi_is_max_q, path_a_ops(0), path_a_ops(1))
  val fp8_aligned_min = alignTowardZero(
    fp8_min_product,
    fp8GuardBits,
    s02_fp8_align_shift_q,
    cfg.fp8RetainWidth
  )

  // FP4 is four lanes: two pair adders here, then the final adder is shared with FP8 before S04.
  val fp4_aligned_01 = resizeSInt(path_a_ops(0) +& path_a_ops(1), fp4PairSumWidth)
  val fp4_aligned_23 = resizeSInt(path_a_ops(2) +& path_a_ops(3), fp4PairSumWidth)


  // --- Path B: FP16/BF16 (High Precision) ---


  private val fp16BaseWidth = 24
  private val fp16CrossWidth = 13
  val s02_fp16_base = Wire(UInt(fp16BaseWidth.W))
  val s02_fp16_cross = Wire(UInt(fp16CrossWidth.W))
  val s02_bf16_carrier = Wire(UInt(cfg.highPrecisionMagnitudeWidth.W))
  s02_fp16_base := 0.U
  s02_fp16_cross := 0.U
  s02_bf16_carrier := 0.U

  when(s02_type_q === DataType.bf16) {
    val bf16_fp16_carrier = Cat(s02_mul_3_q, 0.U(cfg.bf16ToFp16CarrierLsbZeros.W))
    s02_bf16_carrier := resizeUInt(bf16_fp16_carrier, cfg.highPrecisionMagnitudeWidth)
  }.elsewhen(s02_type_q === DataType.fp16) {
    // A*B = {Ah*Bh, Al*Bl} + ((Ah*Bl + Al*Bh) << 4).
    // HH occupies [23:8] and LL occupies [7:0], so concatenation is exact wiring.
    s02_fp16_base := Cat(s02_mul_3_q, s02_mul_0_q)
    s02_fp16_cross := s02_mul_2_q +& s02_mul_1_q
  }

  // ==============================================================================
  // S03 操作数寄存器
  // ==============================================================================
  val s03_type_q     = RegEnable(s02_type_q, s02_fire)
  val s03_fp8_max_product_q = RegEnable(fp8_max_product, s02_fire)
  val s03_fp8_aligned_min_q = RegEnable(fp8_aligned_min, s02_fire)
  val s03_fp4_pair01_q = RegEnable(fp4_aligned_01, s02_fire)
  val s03_fp4_pair23_q = RegEnable(fp4_aligned_23, s02_fire)
  val s03_fp16_base_q = RegEnable(s02_fp16_base, s02_fire)
  val s03_fp16_cross_q = RegEnable(s02_fp16_cross, s02_fire)
  val s03_bf16_carrier_q = RegEnable(s02_bf16_carrier, s02_fire)
  val s03_sign_q = RegEnable(s02_sign_q(0), s02_fire)

  // ==============================================================================
  // S03 -> S04: 低精度末级加法 / FP16 CPA 与符号转换
  // ==============================================================================
  val s03_is_fp8 = isFP8Family(s03_type_q)
  // Both families enter the shared adder in their final SubPE output layout:
  // useful bits occupy the high side and all available fractional guard positions are low zeros.
  val s03_fp8_aligned_max =
    if (fp8GuardBits > 0)
      Cat(s03_fp8_max_product_q.asUInt, 0.U(fp8GuardBits.W)).asSInt
    else s03_fp8_max_product_q
  val s03_fp8_op_max = placeAtOutput(s03_fp8_aligned_max, fp8OutputLsbZeros)
  val s03_fp8_op_min = placeAtOutput(s03_fp8_aligned_min_q, fp8OutputLsbZeros)
  val s03_fp4_op_01 = placeAtOutput(s03_fp4_pair01_q, fp4OutputLsbZeros)
  val s03_fp4_op_23 = placeAtOutput(s03_fp4_pair23_q, fp4OutputLsbZeros)
  val s03_path_a_op_a = Mux(s03_is_fp8, s03_fp8_op_max, s03_fp4_op_01)
  val s03_path_a_op_b = Mux(s03_is_fp8, s03_fp8_op_min, s03_fp4_op_23)
  val s03_path_a_sum = s03_path_a_op_a +& s03_path_a_op_b

  val s03_high_prec_mag = Wire(UInt(cfg.highPrecisionMagnitudeWidth.W))
  s03_high_prec_mag := 0.U
  when(s03_type_q === DataType.bf16) {
    s03_high_prec_mag := s03_bf16_carrier_q
  }.elsewhen(s03_type_q === DataType.fp16) {
    // The wide FP16 CPA and signed conversion both feed S04; constant shift is wiring.
    val cross_aligned = (s03_fp16_cross_q << 4).pad(fp16BaseWidth)
    val fp16_decoded_product = (s03_fp16_base_q +& cross_aligned)(fp16BaseWidth - 1, 0)
    s03_high_prec_mag := fp16_decoded_product(fp16BaseWidth - 1, cfg.fp16ProductDroppedLsb)
  }
  // S04: combine the FP16 CPA and magnitude-to-complement conversion.
  // Low-precision sums already have their final binary point.
  val final_result = Mux(isHighPrecision(s03_type_q),
    exportHighPrecisionResult(s03_high_prec_mag, s03_sign_q),
    resizeSInt(s03_path_a_sum, cfg.outWidth))
  val s04_result_q = RegEnable(final_result, s03_fire)
  io.out_data.valid := s04_valid_q
  io.out_data.bits.result := s04_result_q
}

/* Output fixed-point contract: W = S + I + F; I excludes the sign.
 * Format                 W(default) S I F(default)  F for configured W
 * FP16/BF16              29         1 2 26          W-3
 * E5M2/E4M3/E3M2/E2M3     29         1 3 25          W-4
 * E2M1/NVFP4             29         1 8 20          W-9
 * HiF4                   29         1 6 22          W-7
 * FP8 retained single lane: W28 = S1/I2/F25. Signed RTZ only on MIN.
 * Output is visible after 3 clocks; early anchor after 1 clock.
 */
