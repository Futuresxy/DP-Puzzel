# CarrySave：共享算术/合同

对应源码：[CarrySave.scala](../../chisel_src/Utils/CarrySave.scala)。

compressSigned 把至少两项有符号数显式符号扩展到调用者 width，再逐次 3:2 压缩为两行；sumWithCorrection 把无符号 correction 零扩成有符号加项后压缩，最后一次 CPA。sum/carry 内部按模 2^width 表示，调用者必须提供足够增长位避免数值溢出。

Full PG 使用 W33，Mid 使用 alignWidth+2。correction 计数的 bit0 必须与 aligned operand bit0 同一二进制小数点。它补偿负数算术右移 floor 与 RTZ 的差，不应再次乘 scale 或另移位。局部逻辑保留源串行压缩组织，本次未声称是优化后的平衡 CSA 树；只有 MAX 和顶层求和采用树形结构。

无 Module/状态/复位，RegEnable 位于调用处。宽度检查要求所有项不宽于目标。待 SV 检查符号扩展、多个负数 discarded correction、极值抵消、进位增长和总和等价性；后续时序证据再决定是否改压缩拓扑。
