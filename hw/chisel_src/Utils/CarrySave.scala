package dp.utils

import chisel3._

object CarrySave {
  private def resizeSigned(value: SInt, width: Int): UInt = {
    require(width >= value.getWidth)
    value.pad(width).asUInt
  }

  private def compress3(a: UInt, b: UInt, c: UInt, width: Int): (UInt, UInt) = {
    val sum = a ^ b ^ c
    val majority = (a & b) | (a & c) | (b & c)
    val shifted_carry = majority << 1
    (sum, shifted_carry(width - 1, 0))
  }

  /** Compress signed two's-complement addends to two modulo-2^width rows. */
  def compressSigned(inputs: Seq[SInt], width: Int): (SInt, SInt) = {
    require(inputs.length >= 2)
    require(inputs.forall(_.getWidth <= width))

    var rows = inputs.map(resizeSigned(_, width)).toList
    while (rows.length > 2) {
      val (sum, carry) = compress3(rows(0), rows(1), rows(2), width)
      rows = sum :: carry :: rows.drop(3)
    }
    (rows(0).asSInt, rows(1).asSInt)
  }

  /** Fuse deferred alignment corrections into the reduction, with one final
    * carry-propagate adder. The caller supplies the full sum width; correction
    * bit zero has the same binary point as the aligned operands' bit zero.
    */
  def sumWithCorrection(inputs: Seq[SInt], correction: UInt, width: Int): SInt = {
    val (sum, carry) = compressSigned(correction.zext +: inputs, width)
    sum + carry
  }
}
