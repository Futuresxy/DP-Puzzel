# MNPE.scala：一个 PE 的完整 MAC 输出

对应源码：[MNPE.scala](../../chisel_src/core/MNPE.scala)。顶层 `MN_PE_<HQE>`，非默认对齐窗口追加 `_W<width>`。例如 `MN_PE_H16Q32E64`、`MN_PE_H0Q32E64`、`MN_PE_H0Q0E32`。

MN-PE 内只有一个 PE；在 M/N 维复制多少 MN-PE 是后续阵列的职责，不增加 N 后缀，也不在本模块组织多个 PE。参数 p 直接传给 PE，所以改变 h/q/e 即改变每次独立输出的 K 计算容量。

`MNInput` 原子包含 `dot:PEInput` 和 `acc:AccControl`，没有彼此等待的独立 AB/C ready。数据流为：PE 生成带 scale dot → Accumulate 加一个 C → LZD/归一化 → Fp32Pack → 一个 FP32 D。内部物理模块仅为 PE 和 Fp32Pack；其他算术在顶层展开。

PE S11 输出，MN 顶层 S18 输出，II=1、无反压。运行格式、C 格式、rounding、last 均按事务采样，可相邻周期变化。同步复位丢弃在途有效事务，数据无需复位。每一笔是独立 `D=dot(A,B)+C`，没有跨拍 C 反馈。

位宽和数值合同由 [PE](../pe/PE.md)、[Accumulate](Accumulate.md)、[Fp32Pack](../common/Fp32Pack.md) 共同定义。输出 D 为 FP32；不把 H/Q/E 同拍相加为总算力。非法格式/舍入是输入合同违例，在有效输入时断言。

需要审查：单 PE 的实际 family 裁剪、C 与 dot 对齐、输出 last、气泡和复位。当前结构展开不是 RTL 验证，不能继承旧 PETile 的测试通过状态；待用户源码审查后补 SV 精度/时序验收。
