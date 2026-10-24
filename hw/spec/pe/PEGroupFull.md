# PEGroupFull.scala：full 复用通路

对应源码：[PEGroupFull.scala](../../chisel_src/pe/PEGroupFull.scala)。来源 commit 和源文件 SHA-256 见 [迁移指纹](../full-reuse-source.json)。

## 职责与物理结构

保留四个完整 `SubPE` 实例和一个 `DataUnpack`。一个 PEGroup 接受四对 16-bit word，容量 H4/Q8/E16；共享一个 A scale 槽和一个 B scale 槽。所有格式共用局部 MAX、N−1=3 个对齐器、CSA 规约和 W33 输出。NVFP4/HiF4 另经一个紧凑 scale 尾数乘法，跨 PEGroup 对齐属于 MidGroup。

参数固定 `dimk=4,numSF=1,numG0=4,numG1=2`，父类检查 scale 数、HiF4 group bits 和输出位宽。数值合同固定在 `PEGroupFullContract`：SubPE W29 + 2 对齐 guard + 2 求和位 = W33，不在本轮降低精度。

## 接口与数值

`in_data: Valid[PEGroupInput]` 为独立 A/B 数据、格式和 scale。`out_pegroup_anchor` 是 S06 的 signed W11 原始 anchor；`out_pegroup_data` 是 S07 的 W33 signed `mul_scale_mant` 和特殊值 flags，两个通道相差一拍且不能停顿。

| product 模式 | W/S/I/F | PG value |
| --- | --- | --- |
| FP16/BF16 | 33/1/4/28 | R×2^(raw_anchor−2*bias−28) |
| FP8/FP6 canonical | 33/1/5/27 | R×2^(raw_anchor−30−27) |
| MXFP4 E2M1 | 33/1/10/22 | R×2^(raw_anchor−22) |
| NVFP4 或 MX/NV 混合 | 33/1/13/19 | R×2^(raw_anchor−19) |
| HiF4 | 33/1/11/21 | R×2^(raw_anchor−21) |

`raw_anchor = local_MAX + scale_exp_a + scale_exp_b −254`，scale 指数在 unpack 后统一为 bias127。H 的虚拟 scale 为 1，忽略外部 sf 数据。unit scale 尾数为 UQ1.3 的 8，乘积为 64；该路径直接输出局部和。NV/HiF4 从 W33 局部和裁去 18 个经断言检查的结构零位，紧凑有符号和乘 W8 的 scale 尾数积，再补零回公共 W33；这里不是可随意截位的精度优化。

局部对齐先补两零到 W31。MAX lane 旁路，其余做算术右移并返回负数 discarded-nonzero 修正位；修正计数进入 W33 CSA 后恢复逐项 RTZ。移位控制饱和到窗口宽度。全零或抵消为零的局部和在 S06 使用 anchor 最小值 −1024，避免参加 MidGroup MAX；这不是有效数值指数。

## 固定流水与验收

S00 input offer；S01 解包寄存；S02 SubPE 部分乘积/early anchor 与 scale 乘积；S03 MAX/scale 去偏置；S04 SubPE 结果和 shift 控制到齐；S05 对齐/RTZ 修正；S06 CSA 和、zero-masked anchor；S07 scale 尾数与最终数据。总延迟 7、II=1，无反压。valid 同步清零，数据寄存器有效使能且不复位。

待 SV：解包/anchor/数据的严格配对、全符号组合、MAX 平局、零哨兵、scale 极值/零/NaN、unit-scale 旁路、18 零位裁剪断言、MX/NV 混合、连续/气泡/复位。当前无 RTL 通过证据，无 PPA 结论。
