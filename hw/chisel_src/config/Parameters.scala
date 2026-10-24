package dp.config

import chisel3._

/** Programmer-visible elaboration parameters; arithmetic widths grow naturally.
  * qAlignWidth: signed Q lane alignment window (9 product bits + guard bits).
  * groupGuardBits: fractional positions retained before local PG alignment.
  * peAlignWidth/topAlignWidth: signed alignment windows before PE / dot+C sums.
  */
case class AlignmentConfig(
  qAlignWidth: Int = Parameters.qAlignWidth,
  groupGuardBits: Int = Parameters.groupGuardBits,
  peAlignWidth: Int = Parameters.peAlignWidth,
  topAlignWidth: Int = Parameters.topAlignWidth
) {
  require(qAlignWidth >= 26 && qAlignWidth <= 30, "q_align_width must be 26..30")
  require(groupGuardBits >= 2 && groupGuardBits <= 4, "group_guard_bits must be 2..4")
  require(peAlignWidth >= 38 && peAlignWidth <= 48, "pe_align_width must be 38..48")
  require(topAlignWidth >= 38 && topAlignWidth <= 48, "top_align_width must be 38..48")
  require(topAlignWidth >= peAlignWidth, "top_align_width must preserve the PE output window")
  require(peAlignWidth >= math.max(29, qAlignWidth + 1) + groupGuardBits + 2,
    "PE alignment window cannot narrow the widest PG carrier")
  val peResultWidth: Int = peAlignWidth + 2
  val topOperandWidth: Int = topAlignWidth + 2
  val suffix: String = if (qAlignWidth == 28 && groupGuardBits == 2 && peAlignWidth == 40 && topAlignWidth == 40) ""
    else s"_Aq${qAlignWidth}g${groupGuardBits}p${peAlignWidth}t${topAlignWidth}"
  def json: ujson.Value = ujson.Obj("q_align_width" -> qAlignWidth,
    "group_guard_bits" -> groupGuardBits, "pe_align_width" -> peAlignWidth,
    "top_align_width" -> topAlignWidth)
}

/** Central defaults; editing these affects Scala defaults and omitted JSON fields.
  * Explicit versioned JSON/CLI values take precedence and are recorded in exports.
  */
object Parameters {
  val qAlignWidth = 28
  val groupGuardBits = 2
  val peAlignWidth = 40
  val topAlignWidth = 40
}

/** Exactly six approved physical profiles. Family and shape cannot disagree. */
case class PEConfig(profile: String) {
  require(PEConfig.profiles.contains(profile), s"Unknown PE profile: $profile")
  val family: String = profile.split("_")(1)
  val groupCount: Int = if (profile.endsWith("g2")) 2 else 4
  val wordCount: Int = 4 * groupCount
  val h: Int = if (family.contains("H")) wordCount else 0
  val q: Int = if (family.contains("Q")) wordCount * 2 else 0
  val e: Int = if (family.contains("E")) wordCount * 4 else 0
  def precision: PEPrecisionConfig = Precision.forFamily(family)
}
object PEConfig {
  val profiles: Seq[String] = Seq("PE_HQE_g4", "PE_QE_g4", "PE_H_g4", "PE_Q_g4", "PE_E_g4", "PE_E_g2")
  def all: Seq[PEConfig] = profiles.map(PEConfig(_))
}

/** PE, independent MN output, or 1..4 PEs sharing one K reduction and C/D. */
case class DesignConfig(
  top: String = "k",
  layout: Seq[PEConfig] = Seq(PEConfig("PE_HQE_g4")),
  alignment: AlignmentConfig = AlignmentConfig()
) {
  require(Set("pe", "mn", "k").contains(top), "top must be pe, mn or k")
  require(layout.nonEmpty && layout.size <= 4, "layout contains 1..4 PEs")
  require(top == "k" || layout.size == 1, "PE/MN top has exactly one base PE")
  val wordCount: Int = layout.map(_.wordCount).sum
  val capacity: String = s"H${layout.map(_.h).sum}Q${layout.map(_.q).sum}E${layout.map(_.e).sum}"
  val topName: String = (if (top == "pe") layout.head.profile
    else s"${top.toUpperCase}_PE_${capacity}") + alignment.suffix
  def json: ujson.Value = ujson.Obj("schema_version" -> 2, "top" -> top,
    "layout" -> ujson.Arr.from(layout.map(_.profile)), "alignment" -> alignment.json)
}
object DesignConfig {
  private val alignmentKeys = Set("q_align_width", "group_guard_bits", "pe_align_width", "top_align_width")
  private def integer(value: ujson.Value): Int = {
    val n = value.num
    require(n.isWhole && n >= Int.MinValue && n <= Int.MaxValue, "Widths must be integers")
    n.toInt
  }
  def fromJson(root: ujson.Value): DesignConfig = {
    require(root.obj.keySet.subsetOf(Set("schema_version", "top", "layout", "alignment")), "Unknown config field")
    require(integer(root("schema_version")) == 2, "Expected schema_version=2")
    val raw = root.obj.getOrElse("alignment", ujson.Obj())
    require(raw.obj.keySet.subsetOf(alignmentKeys), "Unknown alignment field")
    val defaults = AlignmentConfig()
    def width(key: String, fallback: Int): Int = raw.obj.get(key).map(integer).getOrElse(fallback)
    DesignConfig(root("top").str, root("layout").arr.map(v => PEConfig(v.str)).toSeq,
      AlignmentConfig(width("q_align_width", defaults.qAlignWidth), width("group_guard_bits", defaults.groupGuardBits),
        width("pe_align_width", defaults.peAlignWidth), width("top_align_width", defaults.topAlignWidth)))
  }
  def load(path: os.Path): DesignConfig = fromJson(ujson.read(os.read(path)))
  /** CLI uses --q-align-width N etc.; resolved values are emitted to the manifest. */
  def overrides(config: DesignConfig, args: Seq[String]): DesignConfig = {
    require(args.size % 2 == 0, "Width overrides require --name value pairs")
    val pairs = args.grouped(2).map { pair =>
      require(pair.head.startsWith("--"), "Expected --width-name")
      val key = pair.head.drop(2).replace('-', '_')
      require(alignmentKeys(key), s"Unknown width override: ${pair.head}")
      key -> pair(1).toInt
    }.toSeq
    require(pairs.map(_._1).distinct.size == pairs.size, "Duplicate width override")
    val json = config.json
    pairs.foreach { case (key, value) => json("alignment")(key) = ujson.Num(value) }
    fromJson(json)
  }
}

object Resource {
  val dimK = 16
  val groupDimK = 4
  val groupNumSF = 1
  val groupG0Count = 4
  val groupG1Count = 2
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
