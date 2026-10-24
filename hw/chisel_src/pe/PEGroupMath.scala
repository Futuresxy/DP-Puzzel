package dp.pe

import chisel3._
import chisel3.util._

/** Stateless fixed-point helpers shared by the five handwritten PEGroup paths. */
private[pe] object PEGroupMath {
  def resizeSInt(value: SInt, width: Int): SInt = {
    require(width > 0, s"signed resize width must be positive, got $width")
    val out = Wire(SInt(width.W))
    if (value.getWidth > width) out := value.asUInt(width - 1, 0).asSInt
    else out := value.pad(width)
    out
  }

  def appendZeros(value: SInt, zeros: Int): SInt = {
    require(zeros >= 0, s"zero padding must be non-negative, got $zeros")
    if (zeros == 0) value else Cat(value.asUInt, 0.U(zeros.W)).asSInt
  }

}
