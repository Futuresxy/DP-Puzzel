package dp.config

import chisel3._

case class PEPrecisionConfig(
  name: String,
  supportsFP16: Boolean = true,
  supportsBF16: Boolean = true,
  supportsFP8: Boolean = true,
  supportsFP6: Boolean = true,
  supportsE2M1: Boolean = true,
  supportsNVFP4: Boolean = true,
  supportsHiF4: Boolean = true
) {
  val supportsHighPrecision: Boolean = supportsFP16 || supportsBF16
  val supportsFP8Family: Boolean = supportsFP8 || supportsFP6
  val supportsFP4: Boolean = supportsE2M1 || supportsNVFP4 || supportsHiF4
  val supportsFP4Family: Boolean = supportsFP4

  require(
    supportsHighPrecision || supportsFP8Family || supportsFP4Family,
    s"precision config '${name}' must enable at least one family"
  )

  def supportsDataTypeCode(dataTypeCode: Int): Boolean =
    dataTypeCode match {
      case code if code == DataType.fp16.litValue.toInt  => supportsFP16
      case code if code == DataType.bf16.litValue.toInt  => supportsBF16
      case code if code == DataType.e5_m2.litValue.toInt  => supportsFP8
      case code if code == DataType.e4_m3.litValue.toInt  => supportsFP8
      case code if code == DataType.e3_m2.litValue.toInt  => supportsFP6
      case code if code == DataType.e2_m3.litValue.toInt  => supportsFP6
      case code if code == DataType.e2_m1.litValue.toInt  => supportsE2M1
      case code if code == DataType.nvfp4.litValue.toInt => supportsNVFP4
      case code if code == DataType.hi_f4.litValue.toInt  => supportsHiF4
      case _ => false
    }

  def supportsDataType(dataType: UInt): Bool = {
    val checks = Seq(
      if (supportsFP16) Some(dataType === DataType.fp16) else None,
      if (supportsBF16) Some(dataType === DataType.bf16) else None,
      if (supportsFP8) Some(dataType === DataType.e5_m2) else None,
      if (supportsFP8) Some(dataType === DataType.e4_m3) else None,
      if (supportsFP6) Some(dataType === DataType.e3_m2) else None,
      if (supportsFP6) Some(dataType === DataType.e2_m3) else None,
      if (supportsE2M1) Some(dataType === DataType.e2_m1) else None,
      if (supportsNVFP4) Some(dataType === DataType.nvfp4) else None,
      if (supportsHiF4) Some(dataType === DataType.hi_f4) else None
    ).flatten
    checks.reduceOption(_ || _).getOrElse(false.B)
  }
}

object Precision {
  val h = PEPrecisionConfig("H", supportsFP8 = false, supportsFP6 = false,
    supportsE2M1 = false, supportsNVFP4 = false, supportsHiF4 = false)
  val q = PEPrecisionConfig("Q", supportsFP16 = false, supportsBF16 = false,
    supportsE2M1 = false, supportsNVFP4 = false, supportsHiF4 = false)
  val e = PEPrecisionConfig("E", supportsFP16 = false, supportsBF16 = false,
    supportsFP8 = false, supportsFP6 = false)
  val hqe = PEPrecisionConfig("HQE")
  val qe = PEPrecisionConfig("QE", supportsFP16 = false, supportsBF16 = false)
  def forFamily(family: String): PEPrecisionConfig = family match {
    case "H" => h
    case "Q" => q
    case "E" => e
    case "HQE" => hqe
    case "QE" => qe
  }
}
