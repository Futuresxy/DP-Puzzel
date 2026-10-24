# LeadingZeroCounter.scala：独立组合 LZD 接口

对应源码：[LeadingZeroCounter.scala](../../chisel_src/core/LeadingZeroCounter.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

一个组合Module，in_data为W位UInt，out_count为ceil(log2(W+1))位，调用BalancedLeadingZero。用于最终LzdNormalize，保留原工程独立模块边界；Mid/C的inline LZD不因此变成同一共享物理实例。

W要求正，零返回W，支持非二次幂。无valid、寄存、延迟或复位；clock/reset为Chisel默认但无状态使用。待SV验证输出范围和one-hot/全零，结构导出须一模块一文件并映射回本文件。
