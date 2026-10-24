package dp.common

import chisel3._
import chisel3.util._

/** Binary split LZD: each level selects the occupied half and one count bit.
  * Padding goes below the operand, preserving the leading-zero count of every
  * nonzero input. Zero returns the actual operand width, including odd widths.
  */
object BalancedLeadingZero {
  def count(value: UInt): UInt = {
    val width = value.getWidth
    require(width > 0)
    val treeWidth = 1 << log2Ceil(width)
    val padded = if (treeWidth == width) value else Cat(value, 0.U((treeWidth - width).W))
    def split(bits: UInt, size: Int): (Bool, UInt) = {
      if (size == 1) (bits(0), 0.U(1.W))
      else {
        val half = size / 2
        val (high_valid, high_count) = split(bits(size - 1, half), half)
        val (low_valid, low_count) = split(bits(half - 1, 0), half)
        val count = if (size == 2) (!high_valid).asUInt
          else Cat(!high_valid, Mux(high_valid, high_count, low_count))
        (high_valid || low_valid, count)
      }
    }
    val (nonzero, count) = split(padded, treeWidth)
    Mux(nonzero, count, width.U(math.max(1, log2Ceil(width + 1)).W))
  }
}
