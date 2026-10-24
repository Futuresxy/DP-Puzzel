package dp.config

import chisel3._

/** Only tunable full-baseline parameters. All numerical widths below are fixed. */
case class DesignConfig(midGroups: Int = 1, alignWidth: Int = 40) {
  require(midGroups >= 1 && midGroups <= 4, "PETile contains 1..4 complete Full MidGroups")
  require(alignWidth >= 40 && alignWidth <= 64, "Full alignment window must be 40..64 bits")
  val wordCount: Int = midGroups * 16
  val capacity: String = s"H${wordCount}Q${wordCount * 2}E${wordCount * 4}"
  val widthSuffix: String = if (alignWidth == 40) "" else s"_W${alignWidth}"
  val topName: String = s"PETile_${capacity}${widthSuffix}"
  def json: ujson.Value = ujson.Obj("schema_version" -> 1,
    "mid_groups" -> midGroups, "align_width" -> alignWidth)
}

object DesignConfig {
  def fromJson(root: ujson.Value): DesignConfig = {
    require(root.obj.keySet == Set("schema_version", "mid_groups", "align_width"),
      "Expected exactly schema_version, mid_groups and align_width")
    def integer(value: ujson.Value): Int = {
      val number = value.num
      require(number.isWhole && number >= Int.MinValue && number <= Int.MaxValue,
        "Parameters must be integers")
      number.toInt
    }
    require(integer(root("schema_version")) == 1, "Unsupported config schema version")
    DesignConfig(integer(root("mid_groups")), integer(root("align_width")))
  }
  def load(path: os.Path): DesignConfig = fromJson(ujson.read(os.read(path)))
}

object Resource {
  val dimK = 16
  val groupDimK = 4
}

object FPBias {
  val fp32Bias = 127
  val e8Bias = 127
  val e6Bias = 48 // HiF4
  val fp16Bias = 15
  val bf16Bias = 127
  val e4Bias = 7
  val e5Bias = 15
  val e3Bias = 3
  val e2Bias = 1
}

object FPMAX {
  val e6Max = 63
  val e5Max = 31
  val e4Max = 15
  val e3Max = 7
  val e2Max = 3
  val e8Max = 255
}

/** Runtime encoding shared by the unpackers and precision selectors. */
object DataType {
  val len = 4

  val fp32 = 12.U(len.W)
  val int32 = 13.U(len.W)
  val tf32 = 14.U(len.W)
  val mxint8 = 9.U(len.W)
  val mxint6 = 10.U(len.W)
  val mxint4 = 11.U(len.W)
  val fp16 = 8.U(len.W)
  val bf16 = 7.U(len.W)
  val e5_m2 = 6.U(len.W)
  val e4_m3 = 5.U(len.W)
  val e3_m2 = 4.U(len.W)
  val e2_m3 = 3.U(len.W)
  val hi_f4 = 2.U(len.W)
  val e2_m1 = 1.U(len.W)
  val nvfp4 = 0.U(len.W)
}

object CDataType {
  val len = 2
  val fp32 = 0.U(len.W)
  val fp16 = 1.U(len.W)
  val bf16 = 2.U(len.W)
}

object MX {
  val scaleTypeWidth = 2
  val none = 0.U(scaleTypeWidth.W)
  val e4_m3 = 1.U(scaleTypeWidth.W)
  val e8_m0 = 2.U(scaleTypeWidth.W)
  val e6_m2 = 3.U(scaleTypeWidth.W)
}

object Design {
  val unpackExpWidth = 10
  val unpackMantWidth = 16
  val unpackSignWidth = 4
  val lzdExpWidth = 11
  val roundExpWidth = lzdExpWidth
  val roundMantWidth = 26
  val subpeOutWidth = 29
  val subpeFP8RetainWidth = 28
  val dotCAddWidth = 40
  val pegroupAlignPadWidth = 2
  val petileMidGroupSize = 4
}

/** Fixed register schedule; no in-flight backpressure. */
object PETilePipeline {
  val subpeLatency = 3
  val pegroupAnchorToData = 1
  val pegroupOutputCycle = 7
  val midgroupOutputCycle = 11
  val cUnpackLatency = 2
  val cRawDelay = midgroupOutputCycle - cUnpackLatency
  val resultCycle = 18
}
