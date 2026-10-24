# RoundPack.scala：两拍 FP32 舍入与打包

对应源码：[RoundPack.scala](../../chisel_src/core/RoundPack.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

只输出FP32，输入W26规范化尾数、unbiased exponentW11、sign/zero/rm/special/last。两个RoundIncrement分别处理normal fraction和subnormal fraction，原工程FuDian依赖由本地组合primitive替换；此处不是继承上游验证结果。

S17计算normal round/sticky、指数偏置+127、舍入进位、overflow和underflow；subnormal右移先饱和到mant宽，对超过全宽的位只保留sticky且round=0，避免RNE把极小数变为伪最小subnormal。S18打包，subnormal进位可成为最小normal。

rm 0/1/2/3/4为RNE/RTZ/RDN/RUP/RMM。overflow按方向取Inf或最大有限数。特殊值优先NaN=0x7fc00000，其次±Inf，再zero，否则finite。仅FP32 out_type=0合法。数据路径此前的RTZ误差不会由最终舍入恢复，不能宣称无限精度FMA的正确舍入。

Valid-only延迟2/II1；valid同步清零，payload RegEnable且不复位，无输出ready。待SV穷举舍入控制、normal ties/进位、subnormal边界、overflow方向、±0/special优先级、last、复位/气泡。
