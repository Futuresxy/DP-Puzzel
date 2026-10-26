package dp.elaborate

import chisel3._
import circt.stage.ChiselStage
import dp.config._
import dp.core._
import dp.utils.PEFactory

/** Structure checks only; no numerical regression or PPA evidence. */
object Elaborate {
  def module(config: DesignConfig): RawModule = config.top match {
    case "pe" => PEFactory.generator(config.layout.head, config.alignment)
    case "mn" => new MN_PE(config.layout.head, config.alignment)
    case "k" => new K_PE(config.layout, config.alignment)
  }
  def check(config: DesignConfig): Unit = {
    val circuit = ChiselStage.emitCHIRRTL(module(config),
      Array("--throw-on-first-error", "--warnings-as-errors"))
    val modules = "(?m)^  module ([^ :]+)".r.findAllMatchIn(circuit).map(_.group(1)).toVector
    // H/Q own their complete arithmetic; only HQE/QE/E instantiate PG/SubPE.
    val grouped = config.layout.filter(p => Set("HQE", "QE", "E")(p.family))
    require(modules.count(_.startsWith("PEGroup_")) == grouped.map(_.groupCount).sum)
    require(modules.count(_.startsWith("SubPE_")) == grouped.map(_.wordCount).sum)
    require(!modules.exists(n => n.startsWith("PEAlignNormalize") || n.startsWith("PEGlobalAlignNormalize")))
    println(s"elaborated ${config.topName}: ${modules.size} definitions, " +
      s"${grouped.map(_.groupCount).sum} PEGroups, ${grouped.map(_.wordCount).sum} SubPEs; ${config.alignment.json}")
  }
  def main(args: Array[String]): Unit = {
    require(args.nonEmpty, "Elaborate review | config <JSON> [--pe-align-width N ...]")
    args.head match {
      case "review" =>
        PEConfig.all.foreach(p => check(DesignConfig("pe", Seq(p))))
        PEConfig.all.foreach(p => check(DesignConfig("mn", Seq(p))))
        Seq(
          Seq("PE_HQE_g4", "PE_E_g2"), Seq("PE_HQE_g4", "PE_E_g4"),
          Seq("PE_HQE_g4", "PE_QE_g4"), Seq("PE_H_g4", "PE_Q_g4", "PE_E_g4")
        ).foreach(names => check(DesignConfig("k", names.map(PEConfig(_)))))
        for (a <- Seq(AlignmentConfig(26, 2, 38, 38), AlignmentConfig(30, 4, 48, 48), AlignmentConfig(28, 2, 40, 44));
             p <- PEConfig.all) check(DesignConfig("pe", Seq(p), a))
        check(DesignConfig("k", Seq(PEConfig("PE_HQE_g4"), PEConfig("PE_E_g2")), AlignmentConfig(30, 4, 48, 48)))
        val invalid: Seq[() => Any] = Seq(
          () => AlignmentConfig(qAlignWidth = 25), () => AlignmentConfig(qAlignWidth = 31),
          () => AlignmentConfig(groupGuardBits = 1), () => AlignmentConfig(groupGuardBits = 5),
          () => AlignmentConfig(peAlignWidth = 37), () => AlignmentConfig(peAlignWidth = 49),
          () => AlignmentConfig(topAlignWidth = 37), () => AlignmentConfig(topAlignWidth = 49),
          () => AlignmentConfig(peAlignWidth = 44, topAlignWidth = 40),
          () => PEConfig("PE_HQE_g2"), () => DesignConfig("mn", PEConfig.all.take(2)))
        invalid.foreach { build =>
          val rejected = try { build(); false } catch { case _: IllegalArgumentException => true }
          require(rejected, "Illegal configuration accepted")
        }
        println(s"rejected ${invalid.size} illegal configurations")
      case "config" =>
        require(args.length >= 2)
        check(DesignConfig.overrides(DesignConfig.load(os.Path(args(1), os.pwd)), args.drop(2).toSeq))
      case other => throw new IllegalArgumentException(s"Unknown command: $other")
    }
  }
}
