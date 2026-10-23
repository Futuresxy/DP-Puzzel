# PE.scala：扁平的带 scale 点积

对应源码：[PE.scala](../../chisel_src/pe/PE.scala)。一个 `PE(p)` 生成一个 `PE_H…Q…E…` Module，内部不实例化 SubPE、PEGroup 或 MidGroup；原先的前两层成为本文件中的运算区域和局部生成函数。

## 输入、输出和组织

输入 `Valid[PEInput]`，包含独立 A/B 格式、packed words、scale 和 HiF4 group bits。输出 `Valid[DotResult]` 仅为 A·B，不含 C 或 FP32 舍入。支持范围由 [Parameters](../config/Parameters.md) 决定。一个输入时钟沿采样事务，经过 11 级寄存器后输出；II=1，无反压，所有 valid 同步复位、数据按 valid 使能保持。

每个 word 对应 `sub_H1Q2E4` 等内联区域；每四个 word 对应 `group_H4Q8E16` 等区域；E32 为八个 word/两组，其余为十六个 word/四组。这些分区保留物理的共享 scale 范围，不能因为层级扁平就改成一个任意范围的 scale。

## 共享乘法和静态裁剪

启用 H 时，一个 word 使用 4×4、4×8、8×4、8×8 四个无符号部分乘法器。FP16 的 UQ1.11 尾数拆成低 4 位和高 8 位，重建 `HH<<8 + (HL+LH)<<4 + LL`；解码所补的两个乘积零 LSB 被精确删除。BF16 使用 8×8 路；Q 使用前两路低 4 位；E 使用四路的低 4 位。符号在乘积之后处理，避免把宽有符号乘法器复制到每种模式。

不启用 H 时，Q/E 共享四个 4×4；Q-only 只有两个 4×4；E-only 有四个 4×4。`if (p.hasH/hasQ/hasE)` 是生成时条件，不是运行时 mask。具体综合结果仍待 EDA 验证。

Q 两 lane 先选最大有效指数，MAX 旁路，MIN 在 28-bit 保留域内 RTZ 右移后加符号。零乘积的指数在第一次 MAX 前屏蔽。E 四 lane 先两两相加，再使用同一个末级加法器；Full/Low 的 Q/E 共享物理末级加法器，但小数点随格式不同。

## 位宽和 scale

下表 W=S+I+F，I 不含符号；默认 alignWidth=40。数值必须同时结合指数 anchor，不能单看整数位数比较格式。

| 边界 | H | Q | MXFP4 | NVFP4/混合 MX-NV | HiF4 |
| --- | --- | --- | --- | --- | --- |
| S4 字结果，非 E-only | 29/1/2/26 | 29/1/3/25 | 29/1/8/20 | 29/1/8/20 | 29/1/6/22 |
| S7 组结果，非 E-only | 33/1/4/28 | 33/1/5/27 | 33/1/10/22 | 33/1/13/19 | 33/1/11/21 |
| S4 字结果，E-only | — | — | 11/1/8/2 | 11/1/8/2 | 11/1/6/4 |
| S7 组结果，E-only | — | — | 22/1/13/8 | 22/1/13/8 | 22/1/11/10 |
| S11 公共输出 | 42/1/1/40 | 同左 | 同左 | 同左 | 同左 |

非 E-only 组内 W29 补两个低零，四项求和保留两位进位形成 W33。NV/HiF 的 scale mantissa 在组求和之后乘一次；读取 W33 的有效前缀，仅删除已证明为零的 18 个 LSB，然后恢复相应小数位置。H/MX 的 scale mantissa 为 1，按需只施加 scale exponent。

E-only 相邻两字共享 HiF4 group1，先同 anchor 预加 W12，再补两零形成 W14，用一个 0/1/2-bit 右移器对齐两对，求和 W15；乘 8-bit scale product 的正数 S9 得 W24，裁剪两个结构性零位得 W22。断言检查裁剪零位及最大 shift；裁剪并非误差换面积的实验旋钮。

S7 physical anchor 为组结果 bit W−2 的实际指数。全路径对应偏移：FP16 −27、BF16 −251、Q −26、MXFP4 +9、NVFP4 +12、HiF4 +10；E-only 使用 MX/NV +12、HiF4 +10。偏移来自数据 bias 和整数位数，scale exponent 另加。

## 流水

| 输出级 | 运算 |
| --- | --- |
| S1 | 解码元素/scale、采样 product format |
| S2 | 共享部分乘法、早期字 anchor、scale product/special |
| S3 | Q MIN 对齐或 E 两两相加，FP16 base/cross，组 MAX |
| S4 | 字末级加法、组 shift/anchor 对齐 |
| S5 | 四字组对齐；E-only 为两对间的小位移 |
| S6 | CSA/CPA 组求和 |
| S7 | scale 尾数乘法及物理 anchor |
| S8 | 2/4 个 scale 组放入 W40，对齐并合并 special |
| S9 | 全组求和，内部 W41（两组）或 W42（四组） |
| S10 | 安全绝对值与平衡 LZD |
| S11 | 无损规格化，统一 sign+magnitude+anchor |

所有格式控制按事务流水，连续输入可切换模式；失活周期 S1 数据不更新，后级乘法输入因此保持。没有新增生成时钟或声称完成时钟门控。

## 验收边界

Q 字内、非 E-only 组内、跨组对齐可能有损，采用 RTZ；无损只指结构零裁剪及 S10/S11 规格化。零 scale 或抵消为零的组在跨组 MAX 前排除。禁止把该结构称为数学精确点积。

当前仅通过结构展开，等待用户审查。SV 阶段需覆盖全格式/混合格式、所有零、巨大指数差、严重抵消、不同 scale、特殊值、气泡、连续格式切换、复位及所有静态变体。PE 输出的固定点合同与最终 FP32 精度要分别检查。
