package dp.core

import dp.config._
import dp.utils.DotUnit

/** One base PE and independent C/D, for one future M/N output position.
  * This is not an array: fixed 18-stage batch pipeline, II=1, Valid result.
  * Control/valid reset; accepted data cannot stall; final FP32 rounding follows
  * finite-window alignment. Both PE and C/D windows come from alignment.
  */
class MN_PE(
  pe: PEConfig = PEConfig("PE_HQE_g4"),
  alignment: AlignmentConfig = AlignmentConfig()
) extends DotUnit(DesignConfig("mn", Seq(pe), alignment))
