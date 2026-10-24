# RoundIncrement.scala：本地组合舍入增量

对应源码：[RoundIncrement.scala](../../chisel_src/core/RoundIncrement.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

本项目新写的小型primitive，替代源RoundPack对FuDian RoundingUnit的依赖；没有拷贝第三方源码树。输入fraction W=23（一般构造要求W>0）、round、sticky、sign和W3 rm，输出同宽fraction和carry。

inexact=round|sticky。RNE增量=round&(sticky|fraction.bit0)，RTZ=0，RDN=inexact&sign，RUP=inexact&!sign，RMM=round。显式W+1加法分出carry；非法rm默认不增量，但PETile在配置握手断言rm≤4，非法值不是受支持模式。roundsToFinite判断overflow方向是否应输出最大有限数。

组合Module，无状态/流水/复位。Full RoundPack有normal和subnormal两个实例，split RTL可去重其相同定义，不能把定义去重误作运行时资源共享。待SV可穷举rm/sign/round/sticky/LSB及全1进位，再覆盖整个RoundPack；本轮没有数值验证证据。
