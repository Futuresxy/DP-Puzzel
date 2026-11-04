package dp.utils

import chisel3._
import chisel3.util._
import dp.utils.BalancedLeadingZero

class LeadingZeroCounter(width: Int) extends Module {
  val io = IO(new Bundle {
    val in_data = Input(UInt(width.W))
    val out_count = Output(UInt(log2Ceil(width+1).W))
  })

  io.out_count := BalancedLeadingZero.count(io.in_data)
}
