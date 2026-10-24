package dp.common

import chisel3._
import chisel3.util._

/** Combinational routing shared by fixed-latency exponent aligners. */
object MaxLaneAlign {
  /** Balanced MAX tree carrying a stable first-lane-wins index. */
  def maximum(values: Seq[SInt]): (SInt, UInt) = {
    require(values.nonEmpty)
    val width = values.map(_.getWidth).max
    val indexWidth = math.max(1, log2Ceil(values.size))
    class Entry extends Bundle {
      val anchor = SInt(width.W)
      val index = UInt(indexWidth.W)
    }
    val leaves = VecInit(values.zipWithIndex.map { case (value, index) =>
      val entry = Wire(new Entry)
      entry.anchor := value
      entry.index := index.U
      entry
    })
    val winner = leaves.reduceTree((left, right) =>
      Mux(left.anchor >= right.anchor, left, right))
    (winner.anchor, winner.index)
  }

  /** The caller registers maxIndex with the shifts. Lane 0 bypasses shifting
    * every other source is routed exactly once into one of N-1 RTZ shifters.
    */
  def apply(data: Seq[SInt], shifts: Seq[UInt], maxIndex: UInt, width: Int): Vec[SInt] = {
    require(data.nonEmpty && data.size == shifts.size)
    require(data.forall(_.getWidth == width))
    val count = data.size
    val inputs = VecInit(data)
    val result = Wire(Vec(count, SInt(width.W)))
    result(0) := inputs(maxIndex)
    val others = (0 until count).map(max => (0 until count).filter(_ != max))
    for (slot <- 0 until count - 1) {
      val value = MuxLookup(maxIndex, data(others.head(slot)))(
        (0 until count).map(max => max.U -> data(others(max)(slot))))
      val shift = MuxLookup(maxIndex, shifts(others.head(slot)))(
        (0 until count).map(max => max.U -> shifts(others(max)(slot))))
      result(slot + 1) := SignedShift.rightTowardZeroToWidth(value, shift, width)
    }
    result
  }

  /** Signed alignment with corrections deferred to the next reduction stage.
    * The first output is the exact MAX lane. The remaining outputs are floors;
    * adding the returned small unsigned count to their sum restores RTZ exactly.
    */
  def withCorrections(
    data: Seq[SInt],
    shifts: Seq[UInt],
    maxIndex: UInt,
    width: Int
  ): (Vec[SInt], UInt) = {
    require(data.size >= 2 && data.size == shifts.size)
    require(data.forall(_.getWidth == width))
    val count = data.size
    val inputs = VecInit(data)
    val result = Wire(Vec(count, SInt(width.W)))
    val corrections = Wire(Vec(count - 1, Bool()))
    result(0) := inputs(maxIndex)
    val others = (0 until count).map(max => (0 until count).filter(_ != max))
    for (slot <- 0 until count - 1) {
      val value = MuxLookup(maxIndex, data(others.head(slot)))(
        (0 until count).map(max => max.U -> data(others(max)(slot))))
      val shift = MuxLookup(maxIndex, shifts(others.head(slot)))(
        (0 until count).map(max => max.U -> shifts(others(max)(slot))))
      val (floor, correction) = SignedShift.rightTowardZeroParts(value, shift, width)
      result(slot + 1) := floor
      corrections(slot) := correction
    }
    (result, PopCount(corrections))
  }

  /** Normalized inputs already have magnitudes. Apply the sign only after
    * logical alignment, preserving signed RTZ without a preceding abs network.
    */
  def fromMagnitudes(
    magnitudes: Seq[UInt],
    negatives: Seq[Bool],
    shifts: Seq[UInt],
    maxIndex: UInt,
    width: Int
  ): Vec[SInt] = {
    require(magnitudes.nonEmpty && magnitudes.size == negatives.size && magnitudes.size == shifts.size)
    require(magnitudes.forall(_.getWidth == width - 1))
    val count = magnitudes.size
    val inputs = VecInit(magnitudes)
    val signs = VecInit(negatives)
    def applySign(magnitude: UInt, negative: Bool): SInt = {
      val positive = magnitude.zext
      Mux(negative, -positive, positive)
    }
    val result = Wire(Vec(count, SInt(width.W)))
    result(0) := applySign(inputs(maxIndex), signs(maxIndex))
    val others = (0 until count).map(max => (0 until count).filter(_ != max))
    for (slot <- 0 until count - 1) {
      val magnitude = MuxLookup(maxIndex, magnitudes(others.head(slot)))(
        (0 until count).map(max => max.U -> magnitudes(others(max)(slot))))
      val negative = MuxLookup(maxIndex, negatives(others.head(slot)))(
        (0 until count).map(max => max.U -> negatives(others(max)(slot))))
      val shift = MuxLookup(maxIndex, shifts(others.head(slot)))(
        (0 until count).map(max => max.U -> shifts(others(max)(slot))))
      result(slot + 1) := applySign(magnitude >> shift, negative)
    }
    result
  }
}
