package dp.core

import dp.config._
import dp.utils.DotUnit

/** 1..4 base PEs reduce disjoint K segments into one C/D output.
  * Fixed physical input slots; supported modes activate only compatible PEs.
  * Stable batch cfg; atomic AB/C admission; 18 stages, II=1, no output stall.
  * Control/valid reset; payload registers hold on bubbles without reset.
  * PE and top alignment windows are passed explicitly, never environment-selected.
  */
class K_PE(
  layout: Seq[PEConfig] = Seq(PEConfig("PE_HQE_g4")),
  alignment: AlignmentConfig = AlignmentConfig()
) extends DotUnit(DesignConfig("k", layout, alignment))
