package dp.utils

import chisel3._
import chisel3.util._

/** Combinational unsigned fraction rounding with a separate carry.
  * rm: 0 RNE, 1 RTZ, 2 RDN, 3 RUP, 4 RMM. No state or reset.
  * This local primitive replaces the source project's FuDian dependency.
  */
class RoundIncrement(width: Int) extends Module {
  require(width > 0)
  val io = IO(new Bundle {
    val in_fraction = Input(UInt(width.W))
    val in_round = Input(Bool())
    val in_sticky = Input(Bool())
    val in_sign = Input(Bool())
    val in_rm = Input(UInt(3.W))
    val out_fraction = Output(UInt(width.W))
    val out_carry = Output(Bool())
  })
  val inexact = io.in_round || io.in_sticky
  val increment = MuxLookup(io.in_rm, false.B)(Seq(
    0.U -> (io.in_round && (io.in_sticky || io.in_fraction(0))),
    1.U -> false.B,
    2.U -> (inexact && io.in_sign),
    3.U -> (inexact && !io.in_sign),
    4.U -> io.in_round))
  val rounded = io.in_fraction +& increment.asUInt
  io.out_fraction := rounded(width - 1, 0)
  io.out_carry := rounded(width)
}

object RoundIncrement {
  def roundsToFinite(rm: UInt, sign: Bool): Bool =
    rm === 1.U || (rm === 2.U && !sign) || (rm === 3.U && sign)
}
