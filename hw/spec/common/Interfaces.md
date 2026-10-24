# Interfaces.scala：数值事务接口

对应源码：[Interfaces.scala](../../chisel_src/common/Interfaces.scala)。定义 Bundle 及特殊值合并函数，没有独立硬件 Module。

接口将一次运算所需数据和控制放在同一事务中，消除源工程 batch cfg、payload 类型和 scale 类型的重复状态。模块用 `Flipped(Valid(...))` 输入和 `Valid(...)` 输出：无 ready、无反压、II=1；消费者必须接收有效输出。复位清空有效流水，数据寄存器无需复位，无效数据不得读取。

| Bundle | 字段 | 含义 |
| --- | --- | --- |
| Operand | data[words]×16 | packed A 或 B，最低索引元素放字的低位 |
| Operand | scale[groups]×8 | 最多覆盖 NVFP4 的每 16 元素一个 scale |
| Operand | group0[words]、group1[words/2] | HiF4 每 4/8 个元素的 1-bit 局部 scale |
| PEInput | a_format、b_format、a、b | 一次完整 A·B，A/B 独立格式与 scale |
| Special | nan、pos_inf、neg_inf | 加法规约所需的规范特殊值状态 |
| DotResult(W) | magnitude[W−1]、negative、anchor[11]、special | 尚未舍入为 FP32 的规格化 dot |
| AccControl | c[32]、c_format[2]、rounding[3]、last | 显式 C 与输出控制；FP16/BF16 C 位于低 16 位 |
| Result | d[32]、last | 一个 FP32 结果及透传标记 |

`Special.seen`/`merge` 保证 NaN 或同时出现 +Inf/−Inf 时规范为 NaN；Inf 符号分开保留。只保留分类，不保留 NaN payload 或 sNaN 异常标志。

DotResult 的数值合同为：

`value = (-1)^negative × magnitude × 2^(anchor − (W−2))`。

非零 magnitude 的最高一位在 W−2；零用 magnitude=0 判断，anchor=-1024 为内部哨兵，不是零的有效指数；special 独立决定最终结果。W 默认 42，提供 41-bit magnitude/40 个小数位置。C 的内部 W25 表示使用 24-bit magnitude/23 个小数位置。

`last` 仅透传，不控制 batch 状态、不自动反馈 D、不保证空闲；相邻事务的 C 必须由调用者提供。此约定避免把外部 C 累加与内部跨周期 accumulator 混淆。

scale 使用范围见 [Decode](Decode.md)。没有提供逐元素 mask；边界 K 不满时由上游在有效 scalar 位置补数值零，同时提供正确的 scale。HiF4 半块需传入原块主 scale 和对应局部 group bits。

待 SV 验收：所有端口位布局、气泡、同步复位打断事务、连续 last/格式变化、独立 A/B scale、不同 PE 实例之间的 C/D 隔离。
