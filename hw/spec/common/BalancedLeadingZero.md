# BalancedLeadingZero.scala：平衡 LZD 组合树

对应源码：[BalancedLeadingZero.scala](../../chisel_src/common/BalancedLeadingZero.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

`count(UInt(W))` 递归二分有效半区，返回前导零数，零输入返回实际 W。非二次幂 W 在低端补零到二次幂，保持非零输入原 leading-zero 数，再对零覆盖为真实宽度。单 bit 也有明确行为。

输入要求已知 W>0；count 用至少 1 bit，并容纳 W（等效 ceil(log2(W+1))）。这是内联组合电路，无 Module/寄存器/复位，调用者负责 valid 和流水寄存。用于 C、MidGroup 和最终规格化，不能把补齐后的树宽当作实际数据宽。

待独立 SV 检查 W=1、奇数宽、全零、每个 one-hot、全一和随机数，与软件 bit_length 的计数一致。结构展开不证明 LZD 数值正确。
