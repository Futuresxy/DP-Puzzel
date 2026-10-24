# FixedPointMeta：共享算术/合同

对应源码：[FixedPointMeta.scala](../../chisel_src/Utils/FixedPointMeta.scala)。

FixedLayout 的 S/I/F 定义在 SubPE，I 不含符号；本对象集中给出各 format 的 Full PG 整数位、bias2x 和 top-anchor 转换，避免跨层根据 W 猜小数点。

PG W33 的 I：H4、Q5、MXFP4 10、NV13、HiF4 11；F=33−1−I。H bias2x=30/254，所有 Q 已重偏为 E5，bias2x30；E 为0。`A_top=raw_anchor−bias2x+I−1` 是 magnitude bit W−2 的指数。Mid 原始和增长 ceil(log2(fanIn)) 位时 anchor 加同样数；normalized anchor=raw+1−LZC。

topAnchoredLayout(W) 要求 W≥3，返回 S1/I1/F(W−2)。格式相关无符号查询与 host Value 函数应一致；anchor 运算先扩宽，在 assertEnable 时检查截回 W11 不溢出。没有独立 Module/流水/复位，断言有效条件由调用者提供。

待 SV 与独立浮点/定点模型检查 H/Q/E 的 bias、NV 混合类型、W38/W48 placement、零哨兵隔离以及规格化 anchor 校正，避免“位宽对了但数值指数差一位”。

此处布局查询以AlignmentConfig传入的Q/PG参数派生；E专用PG使用自身I13/I11坐标，H/Q全局路径使用原始逐项物理anchor，不经过此PG坐标转换。
