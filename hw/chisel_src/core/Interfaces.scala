package dp.core

import dp.config._
import chisel3._

// --- 接口 Bundle 定义 ---

/** 缩放因子接口定义
 *  sf_data 缩放因子 8bit
 *  sf_type 设置E8M0 E4M3 E6M2等格式
 *  sf_group0 0级缩放因子
 *  sf_group1 1级缩放因子
 */
class ScalingFactorBundle(val numSF: Int, val numG0: Int, val numG1: Int) extends Bundle {
  val sf_data   = Vec(numSF, UInt(8.W))
  val sf_type   = UInt(MX.scaleTypeWidth.W)      // E8M0, E4M3, E6M2
  val sf_group0 = Vec(numG0, UInt(1.W)) // HiF4 专用
  val sf_group1 = Vec(numG1, UInt(1.W)) // HiF4 专用
}
/** 拆分后的 A 或 B 向量数据包
 * dimk: 向量长度 Base 16bit
 * numSF: 缩放因子数量。每个 MidGroup 占用与其 PEGroup 数相等的 scale 槽位；
 *        MXFP8/6 和 HiF4 使用每个 MidGroup 第 0 槽，MXFP4 使用第 0/1 槽，
 *        NVFP4 每个 PEGroup 使用一个槽。双组 FP4 MidGroup 使用 MXFP4/HiF4 槽0、
 *        NVFP4 槽0/1；调度层在 HiF4 跨 Tile 拆分时复制相应主 scale 并切分 group bits。
 * numG0: HIF4 专用，group0 数量，每4个HIF4元素一个E1_0
 * numG1: HIF4 专用，group1 数量，每8个HIF4元素一个E1_1
 *
 * data： 以FP16为参考的数据并行集合
 * data_type： 指示数据类型包含FP16 BF16 MXFP8/6/4 NVFP4 HiFP4 等数据类型
 * sf ：      缩放因子的集合，包含多级缩放因子的类型
*/
class VectorInputBundle(val dimk: Int, val numSF: Int, val numG0: Int, val numG1: Int) extends Bundle {
  val data       = Vec(dimk, UInt(16.W))
  val data_type  = UInt((DataType.len).W)
  val sf         = new ScalingFactorBundle(numSF, numG0, numG1)
}


/** PETile AB 输入接口
 * a :输入的a 向量数据、缩放因子集合
 * b :输入的b 向量数据、缩放因子集合
 */
class PETileABInput(dimk: Int = Resource.dimK) extends Bundle {
  val a = new VectorInputBundle(dimk, dimk/4, dimk, dimk/2)
  val b = new VectorInputBundle(dimk, dimk/4, dimk, dimk/2)
  val last = Bool()
}

/** PETile C 累加输入；格式与舍入控制由 batch-level cfg 提供。 */
class PETileCInput extends Bundle {
  val c = UInt(32.W)
}

/** PETile batch-level configuration.
 * This is fixed for one streaming batch. `dataType/sfType` are the A-side
 * controls retained under their historical names; B has independent controls.
 */
class PETileConfig extends Bundle {
  val data_type = UInt(DataType.len.W)
  val b_data_type = UInt(DataType.len.W)
  val sf_type   = UInt(MX.scaleTypeWidth.W)
  val b_sf_type  = UInt(MX.scaleTypeWidth.W)
  val c_type    = UInt(CDataType.len.W)
  val rm       = UInt(3.W)
  val out_type  = UInt(3.W)
}

/** PETile numerical output. Only FP32 packing is implemented. */
class PETileOutput extends Bundle {
  val result = UInt(32.W) // FP32 only
  val last = Bool()
}
