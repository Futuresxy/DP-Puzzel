package dp.utils

import dp.config._
import chisel3._
import chisel3.util._

/*  指数解包输出
  * exp_o 多维度指数
  * scaleexp_o 缩放因子指数
  * type_o 数据类型
 */
class VectorUnpackExpBundle(dimk: Int, expDataWidth: Int, numSF: Int) extends Bundle {
  val pegroup_exp_o      = Vec(dimk, UInt(expDataWidth.W))
  val pegroup_scaleexp_o = Vec(numSF, UInt(8.W))
  val pegroup_type_o    = UInt(DataType.len.W)

}
/*  尾数解包输出
  * mant_o 多维度尾数
  * scalemant_o 缩放因子尾数
  * type_o 数据类型
 */
class VectorUnpackMantBundle(dimk: Int, mantDataWidth: Int, numSF: Int) extends Bundle {
  val pegroup_mant_o      = Vec(dimk, UInt(mantDataWidth.W))
  val pegroup_scalemant_o = Vec(numSF, UInt(4.W))
  val pegroup_type_o      = UInt(DataType.len.W)
}
/*  符号位解包输出*/
class VectorUnpackSignBundle(dimk: Int, signDataWidth: Int) extends Bundle {
  val pegroup_sign_o = Vec(dimk, UInt(signDataWidth.W))
}

/** Per-element operand classification after element and scale are combined. */
class VectorUnpackClassBundle(dimk: Int, classW: Int) extends Bundle {
  val is_nan = Vec(dimk, UInt(classW.W))
  val is_inf = Vec(dimk, UInt(classW.W))
  val is_zero = Vec(dimk, UInt(classW.W))
  val lane_active = Vec(dimk, UInt(classW.W))
}

/*  单向量解包输出接口
  * pegroup_exp_o 指数解包输出
  * pegroup_mant_o 尾数解包输出
  * pegroup_sign_o 符号位解包输出
  * */
class VectorUnpackBundle(dimk: Int, numSF: Int, expW: Int, mantW: Int, signW: Int) extends Bundle {
  val pegroup_exp_o  = new VectorUnpackExpBundle(dimk, expW, numSF)
  val pegroup_mant_o = new VectorUnpackMantBundle(dimk, mantW, numSF)
  val pegroup_sign_o = new VectorUnpackSignBundle(dimk, signW)
  val pegroup_class_o = new VectorUnpackClassBundle(dimk, signW)
}
/*  PEGroupa b向量解包输出接口
  * pegroup_unpack_a  解包输出
  * pegroup_unpack_b  解包输出
  * */
class DataUnpackOutput(
  dimk: Int,
  numSF: Int,
  expW: Int = Design.unpackExpWidth,
  mantW: Int = Design.unpackMantWidth,
  signW: Int = Design.unpackSignWidth
) extends Bundle {
  val pegroup_unpack_a = new VectorUnpackBundle(dimk, numSF, expW, mantW, signW)
  val pegroup_unpack_b = new VectorUnpackBundle(dimk, numSF, expW, mantW, signW)
  // The PEGroup consumes Ti classes only as one canonical additive state.
  // Reduce before the optional unpack output register so lane-local class
  // vectors do not become stored interface state.
  val pegroup_special = new SpecialValueFlags
}

abstract class DataUnpackBase(
  dimk: Int,
  numSF: Int,
  numG0: Int,
  numG1: Int,
  expW: Int = Design.unpackExpWidth,
  mantW: Int = Design.unpackMantWidth,
  signW: Int = Design.unpackSignWidth
) extends Module {
  val io = IO(new Bundle {
    val in_data      = Flipped(Valid(new PEGroupInput(dimk, numSF, numG0, numG1)))
    val out_data = Valid(new DataUnpackOutput(dimk, numSF, expW, mantW, signW))
  })
}
