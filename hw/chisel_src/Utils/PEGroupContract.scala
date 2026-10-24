package dp.utils

import dp.config.PETilePipeline

/** Fixed forward-only schedule; no ready signal may delay an accepted item.
  * All families: aligned S05, sum and zero-masked anchor S06, final result S07.
  * MidGroup registers MAX at S07, then computes deltas and aligns at S08.
  */
object PEGroupContract {
  val anchorWidth: Int = 11
  val anchorToDataLatency: Int = PETilePipeline.pegroupAnchorToData
}
