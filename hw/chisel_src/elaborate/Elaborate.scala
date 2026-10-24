package dp.elaborate

import chisel3._
import circt.stage.ChiselStage
import dp.config._
import dp.core._
import dp.pe.PE

/** Review-only elaboration entry. It emits no RTL files and runs no numerical tests.
  * RTL export is a separate future step with manifest and SV validation gates.
  */
object Elaborate {
  def module(config: DesignConfig): RawModule =
    if (config.kind == "mn") new MNPE(config.pes.head) else new KPE(config.pes)

  def main(args: Array[String]): Unit = {
    require(args.nonEmpty, "Usage: pe.runMain dp.elaborate.Elaborate review | config <file.json> | pe|mn|k <HQE> ...")
    def check(label: String, generator: => RawModule): Unit = {
      val circuit = ChiselStage.emitCHIRRTL(generator, Array("--throw-on-first-error", "--warnings-as-errors"))
      val modules = "(?m)^  module ([^ :]+)".r.findAllMatchIn(circuit).map(_.group(1)).toVector
      require(!modules.exists(n => n.startsWith("SubPE") || n.startsWith("PEGroup") || n.startsWith("MidGroup")))
      println(s"elaborated $label: ${modules.mkString(", ")}")
    }
    if (args.head == "review") {
      require(args.length == 1)
      PEConfig.reviewVariants.foreach { p =>
        check(s"pe/${p.tag}", new PE(p))
        check(s"mn/${p.tag}", new MNPE(p))
      }
      for (count <- 1 to 4) check(s"k/full/$count", new KPE(Seq.fill(count)(PEConfig.full)))
      check("k/full+quarter+eighth+eighthHalf", new KPE(Seq(
        PEConfig.full, PEConfig.quarter, PEConfig.eighth, PEConfig.eighthHalf)))
      check("k/quarter+eighthHalf", new KPE(Seq(PEConfig.quarter, PEConfig.eighthHalf)))
      check("pe/W64", new PE(PEConfig.full.copy(alignWidth = 64)))
      check("mn/W64", new MNPE(PEConfig.eighthHalf.copy(alignWidth = 64)))
    } else if (args.head == "config") {
      require(args.length == 2)
      val config = DesignConfig.load(os.Path(args(1), os.pwd))
      check(config.topName, module(config))
    } else {
      val layout = args.tail.map(PEConfig.parse).toSeq
      require(layout.nonEmpty)
      args.head match {
        case "pe" => require(layout.size == 1); check("pe", new PE(layout.head))
        case "mn" => require(layout.size == 1); check("mn", new MNPE(layout.head))
        case "k" => check("k", new KPE(layout))
        case other => throw new IllegalArgumentException(s"Unknown top kind: $other")
      }
    }
  }
}
