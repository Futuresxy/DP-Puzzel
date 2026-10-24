# SubPE.scala：full 复用通路

对应源码：[SubPE.scala](../../chisel_src/pe/SubPE.scala)。来源 commit 和源文件 SHA-256 见 [迁移指纹](../full-reuse-source.json)。

## 职责与复用结构

一个 SubPE 对应一对已解码的 16-bit packed word，物理容量 H1/Q2/E4。保留原工程 `SubPEFull` 的资源拓扑，类名统一为 `SubPE`，RTL 名 `SubPE_H1Q2E4`。四个无符号部分乘法器分别是 4×4、4×8、8×4、8×8；各模式互斥地选择其输入。

- FP16：12-bit 解码尾数拆成 8-bit 高段和 4-bit 低段；`HH:LL + ((HL+LH)<<4)` 重建乘积，丢弃解码 padding 造成的两个已知零 LSB。
- BF16：只使用 8×8；补零进入高精度公共坐标。
- FP8/FP6：使用两个 4-bit 尾数乘积。低 lane 放在 nibble0，高 lane 放在 nibble2，这是源工程布局，不能改为相邻 nibble 而不同时改解包。
- FP4：四个 4-bit 尾数并行相乘，先两两求和再经与 Q 模式共用的末级加法器规约。HiF4 的局部指数已进入 anchor。

这些是同一套物理资源的模式容量，不能按 H+Q+E 同时累加吞吐。

## 接口与参数

`in_data: Valid[SubPEInput]` 含 `a_exp/b_exp` 各 W10、`a_mant/b_mant` 各 W16、`a_sign/b_sign` 各 W4、`ab_type` W4。格式是 A/B 独立解包后的 canonical product family，并非两侧原始格式。`out_anchor` 为 W9 unsigned 原始指数和，`out_data.result` 为 W29 signed。

`SubPEConfig` 保留解码位宽和固定点元信息以便审查；Full 基线固定 exp/mant/sign/anchor=10/16/4/9、out=29、Q retain=28，不把每个字段当作扫描旋钮。检查最小输入位宽和完整结果容纳关系。

## 数值坐标

`W=S+I+F`，I 不含符号。对于非特殊有限值，`value=R×2^(raw_anchor−2*bias−F)`；H 的 bias 分别为 15/127，Q 已统一为 bias15，E 的局部数值不另减元素 bias。

| 模式 | W/S/I/F | 说明 |
| --- | --- | --- |
| FP16/BF16 | 29/1/2/26 | 原始高精度 product S1/I2/F20 后补 6 零 |
| FP8/FP6 | 29/1/3/25 | 单 lane S1/I2/F6，补 19 guard 位后对齐 |
| E2M1/NVFP4 | 29/1/8/20 | 四 lane 求和 W11 后补 18 零 |
| HiF4 | 29/1/6/22 | 同一 W29，不同二进制小数点 |

Q 只对指数较小的 MIN 路径做 signed RTZ 右移，MAX 保留并旁路，平局保留低 lane；其余结构性补零/裁剪不引入额外舍入。零乘积在首次 MAX 前 anchor 置零，避免大指数零掩盖非零项。NaN/Inf 不走此数值通路，由 PEGroup 的 sideband 合并。

## 周期、复位与验收

以本模块输入 offer 为 L0：L1 部分乘积/anchor；L2 对齐/重建操作数；L3 公共末级和/符号结果。嵌入 PETile 时对应 S02/S03/S04。II=1，Valid 气泡逐拍前进，无 ready 或内部停顿。valid 寄存器同步复位为 0；数据用 RegEnable 在有效时更新，不复位。

待 SV 验收：各 lane 的符号与顺序、FP16 分解重建、Q 指数差 0/1/19/28/超过窗口、负数 RTZ 与严重抵消、零 MAX、连续输入/气泡/复位。结构展开不能证明数值正确。
