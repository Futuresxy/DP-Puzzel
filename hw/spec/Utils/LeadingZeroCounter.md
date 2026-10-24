# LeadingZeroCounter：共享算术/合同

对应源码：[LeadingZeroCounter.scala](../../chisel_src/Utils/LeadingZeroCounter.scala)。

一个组合Module，in_data为W位UInt，out_count为ceil(log2(W+1))位，调用BalancedLeadingZero。用于最终LzdNormalize，保留原工程独立模块边界；Mid/C的inline LZD不因此变成同一共享物理实例。

W要求正，零返回W，支持非二次幂。无valid、寄存、延迟或复位；clock/reset为Chisel默认但无状态使用。待SV验证输出范围和one-hot/全零，结构导出须一模块一文件并映射回本文件。
