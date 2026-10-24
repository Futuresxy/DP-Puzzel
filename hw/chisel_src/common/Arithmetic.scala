package dp.common

import chisel3._
import chisel3.util._

/** Inline circuit builders: no architectural hierarchy and no hidden state. */
object Arithmetic {
  def signed(magnitude: UInt, negative: Bool): SInt = {
    val positive = magnitude.zext
    Mux(negative, -positive, positive)
  }

  def append(value: SInt, bits: Int): SInt = {
    require(bits >= 0)
    if (bits == 0) value else Cat(value.asUInt, 0.U(bits.W)).asSInt
  }

  /** Barrel shift plus discarded-bit OR, including shifts beyond the input width. */
  def shiftSticky(value: UInt, amount: UInt): (UInt, Bool) = {
    val width = value.getWidth
    var shifted = value
    var sticky = false.B
    val stages = math.min(amount.getWidth, log2Ceil(width))
    for (stage <- 0 until stages) {
      val distance = 1 << stage
      sticky = sticky || (amount(stage) && shifted(distance - 1, 0).orR)
      shifted = Mux(amount(stage), (shifted >> distance).pad(width), shifted)
    }
    if (amount.getWidth > stages) {
      val beyond_width = amount(amount.getWidth - 1, stages).orR
      sticky = sticky || (beyond_width && shifted.orR)
      shifted = Mux(beyond_width, 0.U(width.W), shifted)
    }
    (shifted, sticky)
  }

  /** Signed RTZ = arithmetic floor + one deferred correction for negative tails. */
  def shiftRtzParts(value: SInt, amount: UInt): (SInt, Bool) = {
    val width = value.getWidth
    var shifted = value
    var discarded = false.B
    val stages = math.min(amount.getWidth, log2Ceil(width))
    for (stage <- 0 until stages) {
      val distance = 1 << stage
      discarded = discarded || (amount(stage) && shifted.asUInt(distance - 1, 0).orR)
      shifted = Mux(amount(stage), (shifted >> distance).pad(width), shifted)
    }
    if (amount.getWidth > stages) {
      val beyond_width = amount(amount.getWidth - 1, stages).orR
      discarded = discarded || (beyond_width && shifted.asUInt.orR)
      shifted = Mux(beyond_width, Mux(value(width - 1), (-1).S(width.W), 0.S(width.W)), shifted)
    }
    (shifted, value(width - 1) && discarded)
  }

  def delta(maximum: SInt, anchor: SInt, width: Int): UInt = {
    val distance = (maximum.pad(13) - anchor.pad(13)).asUInt
    val controlWidth = math.max(1, log2Ceil(width + 1))
    Mux(distance >= width.U, width.U(controlWidth.W), distance(controlWidth - 1, 0))
  }

  /** Balanced maximum, first input wins a tie. */
  def maximum(values: Seq[SInt]): (SInt, UInt) = {
    require(values.nonEmpty)
    def tree(entries: Seq[(SInt, UInt)]): (SInt, UInt) = {
      if (entries.size == 1) entries.head
      else {
        val (left, right) = entries.splitAt(entries.size / 2)
        val (a, ai) = tree(left)
        val (b, bi) = tree(right)
        (Mux(a >= b, a, b), Mux(a >= b, ai, bi))
      }
    }
    tree(values.zipWithIndex.map { case (value, i) =>
      (value, i.U(math.max(1, log2Ceil(values.size)).W))
    })
  }

  /** Move MAX to slot zero by one swap, so only N-1 barrel shifters exist. */
  def align(values: Seq[SInt], shifts: Seq[UInt], winner: UInt): (Vec[SInt], UInt) = {
    require(values.nonEmpty && values.size == shifts.size)
    val inputs = VecInit(values)
    val shifted = (1 until values.size).map { i =>
      shiftRtzParts(Mux(winner === i.U, values.head, values(i)),
        Mux(winner === i.U, shifts.head, shifts(i)))
    }
    val floors = VecInit(Seq(inputs(winner)) ++ shifted.map(_._1))
    val correction = if (shifted.isEmpty) 0.U(1.W) else PopCount(VecInit(shifted.map(_._2)))
    (floors, correction)
  }

  /** Level-by-level 3:2 compression, then one carry-propagate adder.
    * The caller provides enough carry bits for the mathematical signed sum.
    */
  def sum(values: Seq[SInt], width: Int): SInt = {
    require(values.nonEmpty && values.forall(_.getWidth <= width))
    var rows = values.map(_.pad(width).asUInt)
    while (rows.size > 2) {
      rows = rows.grouped(3).flatMap {
        case Seq(a, b, c) =>
          val carry = ((a & b) | (a & c) | (b & c)) << 1
          Seq(a ^ b ^ c, carry(width - 1, 0))
        case rest => rest
      }.toSeq
    }
    if (rows.size == 1) rows.head.asSInt else (rows.head + rows(1)).asSInt
  }

  /** Balanced leading-zero tree; zero returns width, including odd widths. */
  def leadingZeros(value: UInt): UInt = {
    val width = value.getWidth
    val paddedWidth = 1 << log2Ceil(width)
    val padded = if (width == paddedWidth) value else Cat(value, 0.U((paddedWidth - width).W))
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
    val (nonzero, count) = split(padded, paddedWidth)
    Mux(nonzero, count, width.U(math.max(1, log2Ceil(width + 1)).W))
  }

  /** Fixed forward pipeline; only valid bits reset, bubble data holds. */
  def delay[T <: Data](value: T, valid: Bool, cycles: Int, name: String): T = {
    require(cycles >= 0)
    var data = value
    var enable = valid
    for (stage <- 0 until cycles) {
      data = RegEnable(data, enable).suggestName(s"${name}_${stage + 1}_q")
      enable = RegNext(enable, false.B).suggestName(s"${name}_${stage + 1}_valid_q")
    }
    data
  }
}
