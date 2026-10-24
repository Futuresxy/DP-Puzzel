# MidGroupFull.scala：full 复用通路

对应源码：[MidGroupFull.scala](../../chisel_src/core/MidGroupFull.scala)。来源 commit 和源文件 SHA-256 见 [迁移指纹](../full-reuse-source.json)。

## 组织与资源边界

一个 MidGroupFull 保留 4 个 `PEGroupFull` 实例，合计 16 个 SubPE；每次接收覆盖 H16/Q32/E64。实例还包含 `MidGroupAlignNormalize` 以及其两拍 `MidGroupNormalizeExact`。这两个是规约/规格化辅助模块，没有替代四个 PEGroup 的层级。没有本地 C 或跨事务 accumulator。

`alignWidth` 从 JSON 的 `align_width` 显式传入，Full 配置入口允许 40–64，默认 40。PG W33 补低零放进 W=alignWidth，四项规约加 2 位；公共输出总位宽 `Wout=alignWidth+2`。固定 four-group 组织不扫描 groupCount。

## 输入与 scale 布局

`in_data: Valid[PEGroupInput]` 含 A/B 各 16 个 W16 word、4 个 W8 scale 槽、16 个 g0 bit 和 8 个 g1 bit。`in_cfg` 持续给出 batch 格式。配置必须保持到所有在途事务排空；格式非法为合同违例，不能用无输出表示一次成功接收。

| 格式 | PG0/1/2/3 使用的 scale slot | 元素 block |
| --- | --- | --- |
| FP16/BF16 | 数据被忽略，虚拟 unit scale | 每 word 1 元素 |
| MXFP8/6 | 0/0/0/0 | 32 元素共一个 scale |
| MXFP4 | 0/0/1/1 | 每 32 元素一个 scale |
| NVFP4 | 0/1/2/3 | 每 16 元素一个 scale |
| HiF4 源编码 | 0/0/0/0 | 64 元素共主 scale，另切 g0/g1 |

A/B 独立选 slot，故混合 E2M1/NVFP4 的 scale 边界不同。g0 每 word 一个 bit，g1 每两个 word 一个 bit，按四 word 子块切分。跨 MidGroup 的主 scale 复制由输入布局负责，不能假定 PETile 自动延续一个更大 HiF4 block。

## 对齐与数值

PG S06 anchor 在 S07 求 MAX、保持平局首 lane；零哨兵不参与有效 MAX，全零时内部基准改为 0。S08 精确补零放置后，三个非 MAX 通道按 W40 有限窗口 signed RTZ 对齐；S09 W42 CSA 加法保留求和增长位。特殊值按加法语义独立合并。

对 product 格式整数位 I 与 bias，PG 原始 anchor 转换 `A_pg=raw−2*bias+I−1`。四路和的 `A_raw=MAX(A_pg)+2`。S10/S11 无损规格化，`A_norm=A_raw+1−LZC`，输出 sign/magnitude，默认 W42=S1/I1/F40：`value=(-1)^mid_negative × mid_magnitude × 2^(mid_anchor−40)`。这是已有有限窗口和的精确规格化，不恢复之前 RTZ 丢失位，也不代表无限精度点积。

## 周期与验收

从 MidGroup 输入 S00 到输出 S11，延迟 11、II=1。S01–S07 在子 PG 内，S08 align、S09 sum、S10 abs/LZD、S11 normalized token。`out_mid_data` 为原子 Valid token，含 W41 magnitude、sign、W11 anchor、zero 和特殊值。无反压；控制/valid 同步复位，数据保持且不复位。cfg 由 PETile batch 寄存器保持。

待 SV：不同 block scale 不误合并、A/B 混合 slot 选择、PG anchor 与数据相差一拍、严重抵消、大指数差、全零/特殊值、最小负数规格化、W40/W64、气泡/复位。尚未执行数值验收。
