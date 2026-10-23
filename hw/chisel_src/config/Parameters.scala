package dp.config

/** One location for tunable defaults and fixed numerical/pipeline contracts.
  * Fixed contracts are not sweep knobs: changing one requires a new width proof/spec.
  */
object Parameters {
  val defaultAlignWidth = 40
  val minAlignWidth = 40
  val maxAlignWidth = 64
  val maxKPEs = 4
  val wordBits = 16
  val wordsPerGroup = 4
  val fullWordWidth = 29
  val eighthWordWidth = 11
  val eighthGroupWidth = 22
  val localAlignBits = 2
  val qProductWidth = 9
  val qRetainWidth = 28
  val qGuardBits = qRetainWidth - qProductWidth
  val halfProductWidth = 23
  val scaleFractionBits = 3
  val anchorWidth = 11
  val peLatency = 11
  val resultLatency = 18
}

/** Physical capacity of one PE; H/Q/E are scalar products per accepted cycle.
  * Modes share multipliers, so their capacities must never be added together.
  * See hw/spec/config/Parameters.md for the supported structures and width derivation.
  */
case class PEConfig(h: Int, q: Int, e: Int, alignWidth: Int = Parameters.defaultAlignWidth) {
  require(Set(0, 16).contains(h), "H is 0 or 16")
  require(Set(0, 32).contains(q), "Q is 0 or 32")
  require(Set(0, 32, 64).contains(e), "E is 0, 32 or 64")
  require(h + q + e > 0, "At least one precision family is required")
  require(e != 32 || (h == 0 && q == 0), "E32 is a standalone half-size PE")
  require(alignWidth >= Parameters.minAlignWidth && alignWidth <= Parameters.maxAlignWidth,
    s"PE alignment window must be ${Parameters.minAlignWidth}..${Parameters.maxAlignWidth} bits")

  val hasH: Boolean = h != 0
  val hasQ: Boolean = q != 0
  val hasE: Boolean = e != 0
  val onlyE: Boolean = !hasH && !hasQ
  val words: Int = Seq(h, q / 2, e / 4).max
  val groups: Int = words / Parameters.wordsPerGroup
  val wordWidth: Int = if (onlyE) Parameters.eighthWordWidth else Parameters.fullWordWidth
  val groupWidth: Int = if (onlyE) Parameters.eighthGroupWidth
    else wordWidth + Parameters.localAlignBits + 2
  val resultWidth: Int = alignWidth + 2
  val exponentWidth: Int = if (hasQ) 10 else if (hasH) 8 else 1
  val tag: String = s"H${h}Q${q}E${e}"
  val widthSuffix: String = if (alignWidth == Parameters.defaultAlignWidth) "" else s"_W${alignWidth}"
  val subTag: String = s"sub_H${if (hasH) 1 else 0}Q${if (hasQ) 2 else 0}E${if (hasE) 4 else 0}"
  val groupTag: String = s"group_H${if (hasH) 4 else 0}Q${if (hasQ) 8 else 0}E${if (hasE) 16 else 0}"
}

/** Top-level generation parameters; every selected PE remains explicitly visible. */
case class DesignConfig(kind: String, pes: Seq[PEConfig]) {
  require(kind == "mn" || kind == "k", "kind must be mn or k")
  require(pes.nonEmpty && pes.size <= Parameters.maxKPEs, "A design contains 1..4 PEs")
  require(kind != "mn" || pes.size == 1, "MN-PE contains exactly one PE")
  require(pes.map(_.alignWidth).distinct.size == 1, "K-PE alignment widths must match")
  val capacity: String = s"H${pes.map(_.h).sum}Q${pes.map(_.q).sum}E${pes.map(_.e).sum}"
  val topName: String = s"${kind.toUpperCase}_PE_${capacity}${pes.head.widthSuffix}"
  def json: ujson.Value = ujson.Obj("schema_version" -> 1, "kind" -> kind,
    "pes" -> ujson.Arr.from(pes.map(p => ujson.Obj("h" -> p.h, "q" -> p.q,
      "e" -> p.e, "align_width" -> p.alignWidth))))
}

object DesignConfig {
  /** Strict JSON loading: reject unknown fields and fractional numeric parameters. */
  def load(path: os.Path): DesignConfig = {
    val root = ujson.read(os.read(path))
    require(root.obj.keySet == Set("schema_version", "kind", "pes"), "Expected schema_version, kind and pes")
    def integer(value: ujson.Value): Int = {
      val number = value.num
      require(number.isWhole && number >= Int.MinValue && number <= Int.MaxValue, "Parameters must be integers")
      number.toInt
    }
    require(integer(root("schema_version")) == 1, "Unsupported config schema version")
    val pes = root("pes").arr.map { entry =>
      require(entry.obj.keySet == Set("h", "q", "e", "align_width"), "Expected h, q, e and align_width for each PE")
      PEConfig(integer(entry("h")), integer(entry("q")), integer(entry("e")), integer(entry("align_width")))
    }.toSeq
    DesignConfig(root("kind").str, pes)
  }
}

object PEConfig {
  val full: PEConfig = PEConfig(16, 32, 64)
  val half: PEConfig = PEConfig(16, 0, 0)
  val quarter: PEConfig = PEConfig(0, 32, 0)
  val low: PEConfig = PEConfig(0, 32, 64)
  val eighth: PEConfig = PEConfig(0, 0, 64)
  val eighthHalf: PEConfig = PEConfig(0, 0, 32)
  val reviewVariants: Seq[PEConfig] = Seq(full, half, quarter, low, eighth, eighthHalf,
    PEConfig(16, 32, 0), PEConfig(16, 0, 64))

  def parse(tag: String): PEConfig = {
    val pattern = "H([0-9]+)Q([0-9]+)E([0-9]+)".r
    tag match {
      case pattern(h, q, e) => PEConfig(h.toInt, q.toInt, e.toInt)
      case _ => throw new IllegalArgumentException(s"Expected H<number>Q<number>E<number>, got $tag")
    }
  }
}
