# Interfaces.scala：packed 输入与 batch 配置

对应源码：[Interfaces.scala](../../chisel_src/core/Interfaces.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

ScalingFactorBundle 含W8 sf_data数组、W2 sf_type、g0/g1 bit数组。VectorInputBundle 含dimk个W16 word、W4 data_type和scale；PETileABInput 组合A/B和last。PETileCInput携带W32 C，FP16/BF16只用低16位。PETileOutput 是W32 FP32 result与last。

PETileConfig含A/B各自W4 dtype和W2 scale type、W2 C type、W3 rm、W3 out_type（仅0合法）。外部cfg握手后持续锁定到result.last，AB payload重复dtype/scale字段必须一致；保留这些字段是本轮源迁移的接口选择。

每个Full MidGroup分配16 word、4 scale、16 g0、8 g1。MXFP8/6/HiF4用slot0，MXFP4按PG选择0/0/1/1，NV用0/1/2/3。更大PETile按MidGroup连续切分。g0覆盖4个FP4元素，g1覆盖8个；跨MidGroup复制主scale是输入布局职责。

仅Bundle，无独立Module/时钟/复位；接收与18拍输出由PETile定义。接口不会自动补尾块，也没有valid lane mask，尾部需由上游补0。待结构与SV验证字段位宽/顺序、冗余字段一致性、scale block布局与last传播。
