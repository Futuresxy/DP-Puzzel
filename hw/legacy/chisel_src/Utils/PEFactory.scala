package dp.utils

import chisel3._
import dp.config._
import dp.pe.h._
import dp.pe.q._
import dp.pe.e._
import dp.pe.hqe._
import dp.pe.qe._

/** Elaboration-only selection: instantiate exactly one approved PE profile. */
object PEFactory {
  def generator(config: PEConfig, alignment: AlignmentConfig): PEBase = config.family match {
    case "H" => new PE_H(alignment)
    case "Q" => new PE_Q(alignment)
    case "E" => new PE_E(config.groupCount, alignment)
    case "HQE" => new PE_HQE(alignment)
    case "QE" => new PE_QE(alignment)
  }
  def instantiate(config: PEConfig, alignment: AlignmentConfig): PEBase = Module(generator(config, alignment))
}
