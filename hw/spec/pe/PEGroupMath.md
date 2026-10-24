# PEGroupMath.scala：有依据的扩展和零填充

对应源码：[PEGroupMath.scala](../../chisel_src/pe/PEGroupMath.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

resizeSInt 将 SInt 显式符号扩展，或保留低 width bit 后重解释 signed；要求 width>0。appendZeros 追加低端 zeros 位，要求非负，zeros=0 返回原值。对固定点来说 appendZeros 同时增宽 W 和 F，二进制小数点坐标须由调用者维护。

这些是内联组合函数，不创建额外 Module/寄存器/复位。resize 的窄化是模2^width，只有调用者证明被裁部分为符号扩展时才数值无损；不能把 helper 名称当无损承诺。用于 Full PG 的 anchor/scale 输出放置。待 SV 与位级参考核对最小负数和符号扩展边界。
