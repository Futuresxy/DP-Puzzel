# Fp32Pack.scala：FP32 舍入与打包

对应源码：[Fp32Pack.scala](../../chisel_src/common/Fp32Pack.scala)。一个独立 `Fp32Pack` 基础 Module，由 MNPE/KPE 各实例化一次；不依赖 FuDian/HardFloat，不复制外部项目代码。

输入 `Valid[RoundInput]`：26-bit magnitude（hidden、23 fraction、guard、sticky）、sign、S11 unbiased exponent、Special、rounding 和 last。输出 `Valid[Result]`，固定两拍，II=1，无反压。

先判断 exponent<−126 是否需要 subnormal 位移。用 barrel shift 的 discarded-bit OR 合并旧 sticky，再统一进行一次 24-bit significand 舍入，避免先按 normal 舍入后再次 subnormal 舍入的双重舍入。

| rounding 编码 | 行为 |
| --- | --- |
| 0 RNE | guard 且（sticky 或保留 LSB=1）时进位，平局取偶 |
| 1 RTZ | 不进位 |
| 2 RDN | 负数且不精确时增加 magnitude |
| 3 RUP | 正数且不精确时增加 magnitude |
| 4 RMM | guard=1 时进位，平局远离零 |

第一拍完成 subnormal 位移、舍入、指数/溢出判断并存控制；第二拍组合 FP32 sign/exponent/fraction，选择特殊值和输出寄存器。不是用一个组合长路径后接无意义的延迟寄存器。

normal 进位可能增加 exponent；subnormal 进位到 bit23 成为最小 normal。大于整个 magnitude 的右移只保留 sticky，RNE 不会误生最小 subnormal，定向舍入仍可产生它。溢出根据方向选择最大有限值或有符号 Inf。NaN 固定 0x7fc00000，±Inf 固定编码，输入准确零规范 +0；不输出 IEEE 异常 flags，也不保留 NaN payload/sNaN。

FP32 舍入只针对传入的有限窗口结果，不代表此前 RTZ 对齐满足 IEEE exact FMA，也不能保证抵消后的数学正确舍入。零符号策略刻意保持源工程的 canonical +0，需要由后续验收模型明确采用。

复位只清 valid；数据 RegEnable 在气泡保持。待 SV 验收：tie-even/tie-away、normal 进位、最大有限值溢出、最小 normal 与最大 subnormal 交界、极小值、所有舍入模式/符号、NaN/Inf 优先级和 last 对齐。
