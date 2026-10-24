package dp.config

import chisel3._

/** Wire encodings retained from the source project; scale type is implied by format. */
object Formats {
  val width = 4
  def nvfp4: UInt = 0.U(width.W)
  def mxfp4: UInt = 1.U(width.W)
  def hif4: UInt = 2.U(width.W)
  def e2m3: UInt = 3.U(width.W)
  def e3m2: UInt = 4.U(width.W)
  def e4m3: UInt = 5.U(width.W)
  def e5m2: UInt = 6.U(width.W)
  def bf16: UInt = 7.U(width.W)
  def fp16: UInt = 8.U(width.W)

  def isH(format: UInt): Bool = format === fp16 || format === bf16
  def isQ(format: UInt): Bool = format >= e2m3 && format <= e5m2
  def isE(format: UInt): Bool = format <= hif4
  def isE2M1(format: UInt): Bool = format === mxfp4 || format === nvfp4
  def supports(p: PEConfig, format: UInt): Bool =
    (p.hasH.B && isH(format)) || (p.hasQ.B && isQ(format)) || (p.hasE.B && isE(format))

  def compatible(a: UInt, b: UInt): Bool =
    (isH(a) && a === b) || (isQ(a) && isQ(b)) ||
      (isE2M1(a) && isE2M1(b)) || (a === hif4 && b === hif4)

  def legal(p: PEConfig, a: UInt, b: UInt): Bool =
    supports(p, a) && supports(p, b) && compatible(a, b)

  /** A shared low-precision coordinate follows independent operand decoding. */
  def product(a: UInt, b: UInt): UInt =
    Mux(isH(a), a, Mux(isQ(a), e5m2,
      Mux(a === hif4, hif4, Mux(a === nvfp4 || b === nvfp4, nvfp4, mxfp4))))

  // C wire encodings; D is always FP32.
  def cFp32: UInt = 0.U(2.W)
  def cFp16: UInt = 1.U(2.W)
  def cBf16: UInt = 2.U(2.W)
}
