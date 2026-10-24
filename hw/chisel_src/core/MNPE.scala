package dp.core

import chisel3._
import chisel3.util._
import dp.config.PEConfig
import dp.common._
import dp.pe.PE

class MNInput(p: PEConfig) extends Bundle {
  val dot = new PEInput(p)
  val acc = new AccControl
}

/** One independent M/N output: one PE followed by C addition and FP32 conversion.
  * Latency 18 cycles, initiation interval 1. Replication in M/N belongs to the array.
  */
class MNPE(val p: PEConfig) extends Module {
  override def desiredName: String = s"MN_PE_${p.tag}${p.widthSuffix}"
  val io = IO(new Bundle {
    val in = Flipped(Valid(new MNInput(p)))
    val out = Valid(new Result)
  })
  private val pe = Module(new PE(p))
  pe.io.in.valid := io.in.valid
  pe.io.in.bits := io.in.bits.dot
  io.out := Accumulate(Seq(pe.io.out.bits), io.in.bits.acc, io.in.valid, p.resultWidth)
}
