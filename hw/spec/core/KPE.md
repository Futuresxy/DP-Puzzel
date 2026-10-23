# KPE.scala：1–4 个 PE 的 K 规约

对应源码：[KPE.scala](../../chisel_src/core/KPE.scala)。顶层参数是有序 `Seq[PEConfig]`，包含 1–4 个 PE，对齐窗口必须一致；允许不同家族能力和 E32/E64 混合。

KPE 与 MNPE 的核心差别是所有活跃 PE 的 dot 在 K 方向相加，再加一次 C、只产生一个 D。共享 C 解码、MAX/对齐、末级求和、LZD/归一化、FP32 舍入，避免每个 PE 各自产生 FP32 后再加法的冗余处理。

`KInput` 使用共同的 a_format/b_format，以及按物理 PE 顺序排列的 MixedVec Operand，支持每个 PE 不同 packed-word 数。每个事务有一个 AccControl。没有把多个不同精度任务强行规约到一个 D：同一事务的格式对所有 PE 相同，不支持该模式的 PE 不接收 token，其结果在 S11 显式清零。

例如 `[H16Q32E64,H0Q32E0,H0Q0E64,H0Q0E32]`：

| 模式 | 活跃 PE 索引 | 一个 D 的实际 K |
| --- | --- | --- |
| H | 0 | 16 |
| Q | 0、1 | 64 |
| E | 0、2、3 | 160 |

顶层名称为 `K_PE_H16Q64E160`。一个格式的逻辑 K 按活跃 PE 顺序串接；未活跃槽位没有逻辑 K、数据忽略。相同容量合计不保证相同电路，因此 export config ID 与 manifest 必须保存有序 PE 列表，不能用名字代替配置。

active mask 延迟 11 拍，和对应 PE 结果同步；inactive special 一起屏蔽，不能只把 magnitude 设零而遗留 NaN。每个 PE 保持自己的 scale block 边界，跨 PE 拆分 HiF4 主块需要上游正确复制主 scale。KPE 不重新量化、不重新推导 scale。

所有 PE S11 到达公共加法路径，顶层 S18 输出，II=1、无反压。PE 个数不改变流水拍数，但 N=dotCount+1 项的求和位宽增加 `ceil(log2(N))`，实际 timing 是否满足频率须由后续 DC 验证。C 是事务输入，没有 D 反馈状态。

待 SV 验收：1/2/3/4 PE、均匀和异构布局、每种模式 active mask、连续模式变化、混合 scale、NaN/Inf 屏蔽、抵消、rounding/last/复位；K=1 还应与等配置 MNPE 做结构合同之外的数值一致性验证。
