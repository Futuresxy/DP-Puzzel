package dp.elaborate

import chisel3._
import circt.stage.ChiselStage
import dp.config.DesignConfig
import dp.core.PETile

/** In-memory structure checks only; no DUT simulation or numerical evidence. */
object Elaborate {
  def module(config: DesignConfig): RawModule =
    new PETile(dimk = config.wordCount, alignWidth = config.alignWidth)

  private def check(config: DesignConfig): Unit = {
    val circuit = ChiselStage.emitCHIRRTL(module(config),
      Array("--throw-on-first-error", "--warnings-as-errors"))
    val modules = "(?m)^  module ([^ :]+)".r.findAllMatchIn(circuit).map(_.group(1)).toVector
    val expected = Seq("PETile_" -> 1, "MidGroupFull_" -> config.midGroups,
      "PEGroupFull_" -> (4 * config.midGroups), "SubPE_" -> (16 * config.midGroups))
    expected.foreach { case (prefix, count) =>
      require(modules.count(_.startsWith(prefix)) == count, s"Missing Full hierarchy: $prefix/$count")
    }
    println(s"elaborated ${config.topName}: ${modules.size} module definitions; " +
      expected.map { case (prefix, count) => s"$prefix=$count" }.mkString(", "))
  }

  def main(args: Array[String]): Unit = {
    require(args.nonEmpty, "Usage: Elaborate review | config <file.json>")
    args.head match {
      case "review" | "full-review" =>
        require(args.length == 1)
        (1 to 4).foreach(count => check(DesignConfig(midGroups = count)))
        check(DesignConfig(alignWidth = 64))
        val invalidConfigs: Seq[(String, () => Any)] = Seq(
          "zero MidGroups" -> (() => DesignConfig(midGroups = 0)),
          "five MidGroups" -> (() => DesignConfig(midGroups = 5)),
          "window 39" -> (() => DesignConfig(alignWidth = 39)),
          "window 65" -> (() => DesignConfig(alignWidth = 65)),
          "fractional count" -> (() => DesignConfig.fromJson(ujson.Obj(
            "schema_version" -> 1, "mid_groups" -> 1.5, "align_width" -> 40))),
          "unknown field" -> (() => DesignConfig.fromJson(ujson.Obj(
            "schema_version" -> 1, "mid_groups" -> 1, "align_width" -> 40, "extra" -> 0))),
          "retired kind/pes schema" -> (() => DesignConfig.fromJson(ujson.Obj(
            "schema_version" -> 1, "kind" -> "mn", "pes" -> ujson.Arr()))))
        invalidConfigs.foreach { case (label, build) =>
          val rejected = try { build(); false } catch { case _: IllegalArgumentException => true }
          require(rejected, s"Invalid Full configuration accepted: $label")
          println(s"rejected invalid config: $label")
        }
      case "config" =>
        require(args.length == 2)
        check(DesignConfig.load(os.Path(args(1), os.pwd)))
      case other => throw new IllegalArgumentException(s"Unknown command: $other")
    }
  }
}
