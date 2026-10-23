# Normalize.scala：规格化边界

对应源码：[Normalize.scala](../../chisel_src/common/Normalize.scala)。提供两种内联、固定两拍的规格化电路，以及 `RoundInput` Bundle；不新增计算层级。

共用输入解释：W-bit 有符号整数 R 和 physical anchor A 表示 `R × 2^(A−(W−2))`。先将 R 符号扩展为 W+1 再取绝对值，避免最小负数溢出；对 W 个 magnitude 位做平衡 LZD。

`exact` 用于 PE S10/S11。第一拍存 magnitude/sign/LZC/anchor/special；第二拍把最高一位放到 W−2。正常情况左移 LZC−1；最小负数 LZC=0，其 magnitude 仅有最高位，右移一位仍无损。指数同步变为 `A+1−LZC`。E32 的内部 W41 无损补一位低零，统一到公共 W42。非零 leading bit 和 anchor 的配对不能分离修改。

`forFp32` 用于顶层 S15/S16。第一拍同样取绝对值/LZD；第二拍规格化到内部最高位后，输出 26-bit `hidden + fraction23 + guard + sticky`。最低输出位 OR 汇总所有剩余尾位，交由 Fp32Pack 舍入。这里的 sticky 压缩是明确的最终精度边界，不能用于仍需要后续精确抵消的 PE 中间结果。

零 magnitude 规范 sign=0；PE anchor=-1024，最终 round 输入 exponent=0；special 单独透传。NaN/Inf 的数值占位不会覆盖 special。有效位同步复位，数据寄存器 RegEnable 保持，无 ready/反压。

宽度限制：exact 要求公共输出不窄于输入；forFp32 要求输入至少 26 位；anchor 为固定 S11，当前参数范围足够。规格化只保留已经进入本级的数值，不能恢复前面 RTZ 丢失的低位。

待 SV 验收：最小负数、全零、最高/最低单比特、奇数位宽、归一化指数补偿、sticky-only 尾数和严重抵消。当前不提供“正确舍入无限精度点积”的承诺。
