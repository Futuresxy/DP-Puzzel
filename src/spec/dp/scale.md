> 功能：定义 scale 统一解包和 bias 处理；范围：E8M0/E4M3/E6M2 到 E8M3、组内融合及统一指数坐标；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（模块文件未建；计划参数入口为 src/chisel/parameter/，未创建）。

# scale 统一 E8M3 数值表示

状态：用户确定三种 scale 统一成 8 位指数 + I1F3 幅值的内部表示；S1 解包，S2 并行形成指数和及 4×4 系数积，S5 对需要的路径应用系数。内部 E8M3 是字段记录，不是新的外部 IEEE 编码。

## 单侧 scale

内部记录为 `scale_exp[7:0]`、`scale_mant[3:0]` 及独立分类。有限值公式：

```text
scale_value = scale_mant × 2^(-3) × 2^(scale_exp - scale_common_bias)
scale_common_bias = 127
```

| 外部 scale / 适用格式 | 解包指数 | I1F3 coefficient | 特殊编码 |
| --- | --- | --- | --- |
| E8M0 / MXFP8/6/4 | 原始八位 e | 8，即 1.0 | 0xff 为 NaN；e=0 为 2^-127，不是零 |
| 非负 E4M3 / NVFP4 | 正规 e+(127-7)，非正规 1+(127-7) | 正规 {1,f[2:0]}，非正规 {0,f[2:0]} | 低七位 0x7f 为 NaN；全零为零；e=15 且 f≤6 仍为有限数 |
| E6M2 / HiF4 | e+(127-48) | {1,f[1:0],0} | 0xff 为 NaN；hidden bit 恒为 1，无零/Inf/subnormal |
| 虚拟单位 scale / T/H/INT8 | 127 | 8 | 无 scale 运算 |

NVFP4 的 scale 采用非负 E4M3：bit7=0 为合法输入约束，负 scale/保留编码的接口报错策略待模式合法性合同冻结，不能静默忽略 bit7。额外 per-tensor scale 不自动添加到本 DP 接口；若需要由上层折入 C/D 之外的缩放或另提明确合同。

bias 和字段宽度集中在格式参数中。8 位指数相加产生 9 位结果，4 位系数相乘产生 8 位 coefficient，小数位为 6；这些结果不能截回输入宽度。

## 应用顺序与旁路

每个基本组已经接收按原量化块广播的 A/B scale。局部乘积先按基本组公共元素 anchor 对齐并求和；HiF4 e1 在 S1 融入元素幅值、e2 在 S3 完成局部对齐。S5 对基本组部分和乘 A/B 的 scale 系数积，再输出 sign/magnitude 组 token。

MX 的 E8M0 系数积恒为 64，解释为 I2F6 即 1.0，省去数据乘法，只把 scale 指数计入 anchor。NVFP4/HiF4 需要系数乘法。scale 为零或 NaN 时仍按特殊值合同处理；不能用零系数屏蔽非法 0×Inf。

## bias 的唯一去除位置

用语义公式约束各段，令 r 为 S2 得到的基本组公共元素原始指数和：

```text
alpha_group = r - element_bias_a - element_bias_b
              + scale_exp_a + scale_exp_b - 2*scale_common_bias
value_group = signed_coefficient × 2^(alpha_group - F_group)
```

T/BF16 元素 bias 为 127，FP16 为 15，Q 在重编码后统一为 15，E 定点元素 bias 为 0；HiF4 的 r 是两侧剩余 e2 的和及其组公共最大值。INT8 无浮点 bias。

S2 可以保留原始指数和，在 S3–S5 的独立标量路径预先减去 scale 双偏置、形成元素双偏置修正；最迟在 S6 与 C 比较前完成。S8 只根据最终无偏指数编码 FP32 并加一次输出 bias，不能再次扣除已处理的元素/scale bias。

用户提出“到 C 比较时处理 bias”在数学上可行；为缩短 S6，当前候选把固定修正提前计算，S6 消费修正后的 anchor。移动固定加减法不改变数值公式，不引入额外周期。

## 历史代码依据

[PEGroup_HQE](../../../hw/legacy/chisel_src/pe/PE_HQE/PEGroup_HQE.scala) 的 S03 先减 scale 的 2×127；[PE_HQE](../../../hw/legacy/chisel_src/pe/PE_HQE/PE_HQE.scala) 与 [FixedPointMeta](../../../hw/legacy/chisel_src/Utils/FixedPointMeta.scala) 使用 `raw_anchor - 2*element_bias + I - 1` 映射到有效 top anchor。旧 [CUnpacker](../../../hw/legacy/chisel_src/Utils/CUnpacker.scala) 在 C 解包时去 bias 并另做规范化。

~~新版只采用这些数值关系。C 在 S1 一次解包并透传，不复制旧两级 C normalizer；缺省采用有效指数与原始 24 位幅值，在 S8 做最终 LZD/归一化。~~

~~**v1.2 当前定义：** 新版只采用这些数值关系。C 改在 S5 单级解包，S1–S4 保持 raw32，FP32 使用有效指数及原始 M24，不复制旧两级 C normalizer；INT32 C 按本笔类型单独解释。~~

**v1.3：** C仍S5解包，FP32原M24及有效指数另配非正规LZD计数；不复制旧两级C normalizer，也不在S5动态左移。INT32独立解释。

## v1.2：scale datatype 逐笔独立携带

每侧独立 in_scale_a_datatype/in_scale_b_datatype，每个请求的全部同侧槽共用一个类型。支持 E8M0、E4M3、E6M2 及无 scale 的 NONE；NVFP4 仍需要 E4M3，不能从接口遗漏。首版两侧格式相同，scale 类型按 [合法矩阵](interface.md) 对应，但 scale 数值可不同。S1 解包后，scale 系数/指数和控制与请求同步，不从后续输入格式取值。

## v1.2.1：去 bias、MAX 与 unsigned 差值

S5 组 token 的 A 已完成元素/scale bias 与定点坐标修正，C 的 A_c 同样无偏。先对有限非零源做 signed MAX，再在足够宽的 signed 临时量中计算 MAX-anchor，确认非负后转 unsigned 移位量；不能用 unsigned 比较负的无偏指数。S2/S3 的同格式产品相减中，相同的元素双 bias 抵消，因此可以保留 r/p 的带偏置无符号表示。

~~若采用实际指数候选，还需 e=A-clz(m)。MAX(e)-e 非负，但把规格化左移与对齐右移合并后，净位移可以有方向；这不是指数 bias 再次变化。详见 [候选推导](group-normalization-options.md)。~~

~~**v1.3：** 已采用 scale 后 e=A_raw-clz(m) 并同时左移 m；S6 的 MAX(e)-e 为非负无符号右移量。合并为一次双向移位仅作 [对照推导](group-normalization-options.md)，不属于当前两级边界。~~

**本轮最终选择：** scale后LZD只计数z；e=A_raw-z用于比较，d=MAX(e)-e非负，但net=z-d有符号。已选 [一次双向移位](group-normalization-options.md) 为当前首选；bias不重复扣除。

## v1.3：NVFP4 / HiF4 紧凑乘法与 scale 后规格化

用户提出 NVFP4 13×9、HiF4 15×7。这里 9/7 位 scale 系数均含一位恒零符号，实际分别为 unsigned 8/6 位；两路都是 signed SOP 乘非负系数。

| 模式 | 紧凑 SOP（TC） | 两侧 scale 的系数积 | 自然乘积（TC） | 装入 W31 中间槽 |
| --- | --- | --- | --- | --- |
| NVFP4 | W13，S1I10F2 | U8，S0I2F6；正 signed 包装 S1I2F6=W9 | W21，S1I12F8 | 低补 10 零，F18 |
| HiF4 | W15，S1I8F6 | U6，S0I2F4；正 signed 包装 S1I2F4=W7 | W21，S1I10F10 | 低补 10 零，F20 |

NV 的 W15/F4 组和没有 HiF4 e2 移位，其两位 guard 始终为结构零；精确去掉后为 W13/F2。HiF4 的 e2 移位可能消耗 guard，仍用 W15/F6；但统一 I1F3 scale 的每侧 coefficient 低位恒零，S2 产生的 U8/F6 积有两个结构低零，可精确去掉成为 U6/F4。原始 scale E8M3 解包与指数支路保持不变。

```text
sop_drop_NV = e_exact_guard_bits
sop_drop_HiF = 0
scale_drop_NV = 0
scale_drop_HiF = 2*(scale_common_fraction_bits-scale_hif_fraction_bits)
W_sop(mode) = E_group_compact_width - sop_drop(mode)
F_sop(mode) = e_product_fraction_bits(mode)+e_exact_guard_bits-sop_drop(mode)
W_factor(mode) = W_scale_product - scale_drop(mode)
F_factor(mode) = F_scale_product - scale_drop(mode)
W_product(mode) = W_sop(mode)+W_factor(mode)  // signed × unsigned
F_product(mode) = F_sop(mode)+F_factor(mode)
pad_product(mode) = W_group-W_product(mode)
```

参数默认推导得到两个 W21。NV SOP 绝对值≤16×12²=2304；HiF SOP 绝对值≤16×14²×2²=12544。scale 系数积分别≤15²=225、7²=49，因此最终绝对值分别≤518400、614656，均可安全装入 20 位幅值。signed×正 signed 包装得到 W22 时，最高位为冗余符号扩展；禁止不检查范围直接裁位。所有去低零操作须证明整除，不是 RTZ。

**共享结构建议：每基本组一套输入 mux 后的乘法器。** 固定输入宽度按能力集合取 `max(W_sop)=15`（signed）及 `max(W_factor)=8`（unsigned）。NV 符号扩展 SOP；HiF 系数高补零。通用乘积 W23，但这两个合法模式的高两位可证明为符号扩展，保留精确 W21 后再落位。若 RTL 乘法要求两输入同为 signed，则给系数补一位零，原生输出 W24，再依据同一范围证明去冗余位。不得把 unsigned 8 位系数直接解释为 signed 8 位。

运行时 mux 不改变物理位宽；未使用位/整个旁路模式需隔离以减少切换。显式写两套乘法器后 mux 输出不保证工具合并；[Yosys 0.45 的 opt_share](https://yosyshq.readthedocs.io/projects/yosys/en/0.45/cmd/opt_share.html) 就有共同输入等适用条件，此来源仅说明工具共享有条件，不推断 DC 的结果。初版保持一套共享资源的方向，是否进一步定制分块部分积或以两套窄单元换时序，须以同工况综合比较，当前不声称 PPA 已优化。

~~**顺序已确认：乘完 scale 后才取幅值、LZD、左移并重算 anchor。** 上表 F18/F20 只到规格化前；S5 正式浮点出口统一为 M30/F29、e=A_raw-clz(m)。无 scale/单位系数路径在选择后进入同一规格化器。不能先规格化 SOP，再忽略 scale 对最高有效位的影响；也不能把 S5 规格化当成最终 FP32 舍入。~~

**当前确认顺序：** 乘完scale后安全取幅值、LZD只产生z；S5原幅值和A_raw保留，NV/HiF出口F18/F20不变。S6得到E_max后按z-d一次双向移位，等价于先左规格化再右对齐。不得在scale之前检测而忽略最终乘积最高位；S8仍负责最终FP32舍入。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 新建架构合同 | 按用户架构图及后续补充定义本模块；区分已确认结构与待审查的位宽推导，尚无实现或 EDA 证据。 | 用户确认；[流水](pipeline.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 同步本轮接口、C 解包阶段、逐请求控制或资源/验证合同；保留被替代定义。 | 用户本轮要求及确认；[总时间线](../CHANGELOG.md) |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 讨论/说明补充 | 记录组实际指数候选及对应数值、特殊值或资源边界；不改变 v1.2 主路径。 | 用户 LZD/指数/特殊值讨论；[总时间线](../CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 按用户最终选择，S5 scale后LZD仅计数、S6一次双向移位；同步数值/接口/资源/备用周期，保留对照。 | 用户最终双向移位选择；[总时间线](../CHANGELOG.md) |
