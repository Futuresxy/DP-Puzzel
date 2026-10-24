package dp.core

import chisel3._
import chisel3.util._
import dp.config._
import dp.common._
import dp.pe.PE

class KInput(layout: Seq[PEConfig]) extends Bundle {
  val a_format = UInt(Formats.width.W)
  val b_format = UInt(Formats.width.W)
  val a = MixedVec(layout.map(new Operand(_)))
  val b = MixedVec(layout.map(new Operand(_)))
  val acc = new AccControl
}

/** One K-reduced output: 1..4 possibly different PEs share one C and one D path.
  * A mode uses every PE supporting that mode; inactive PE outputs are zero-masked.
  * Input is atomic, latency 18 cycles, initiation interval 1, no internal feedback.
  */
class KPE(val layout: Seq[PEConfig]) extends Module {
  require(layout.nonEmpty && layout.size <= Parameters.maxKPEs, "K-PE contains 1..4 PEs")
  require(layout.map(_.alignWidth).distinct.size == 1, "All PE carriers must have the same alignment width")
  private val p = layout.head
  private val tag = s"H${layout.map(_.h).sum}Q${layout.map(_.q).sum}E${layout.map(_.e).sum}"
  override def desiredName: String = s"K_PE_${tag}${p.widthSuffix}"
  val io = IO(new Bundle {
    val in = Flipped(Valid(new KInput(layout)))
    val out = Valid(new Result)
  })
  private val active = VecInit(layout.map(Formats.legal(_, io.in.bits.a_format, io.in.bits.b_format)))
  when(io.in.valid) { assert(active.asUInt.orR, "K-PE has no PE supporting this operand pair") }
  private val s11_active_q = Arithmetic.delay(active, io.in.valid, 11, "active_s11")
  private val dots = layout.zipWithIndex.map { case (config, index) =>
    val pe = Module(new PE(config)).suggestName(s"pe_${config.tag}_${index}")
    pe.io.in.valid := io.in.valid && active(index)
    pe.io.in.bits.a_format := io.in.bits.a_format
    pe.io.in.bits.b_format := io.in.bits.b_format
    pe.io.in.bits.a := io.in.bits.a(index)
    pe.io.in.bits.b := io.in.bits.b(index)
    Mux(s11_active_q(index), pe.io.out.bits, 0.U.asTypeOf(new DotResult(p.resultWidth)))
  }
  io.out := Accumulate(dots, io.in.bits.acc, io.in.valid, p.resultWidth)
}
