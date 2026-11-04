> 功能：定义 scale 统一解包和 bias 处理；范围：E8M0/E4M3/E6M2 到 E8M3、组内融合及统一指数坐标；版本：v1.2；修改时间：2026-11-04 19:38:52 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（模块文件未建；计划参数入口为 src/chisel/parameter/，未创建）。

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

**v1.2 当前定义：** 新版只采用这些数值关系。C 改在 S5 单级解包，S1–S4 保持 raw32，FP32 使用有效指数及原始 M24，不复制旧两级 C normalizer；INT32 C 按本笔类型单独解释。

## v1.2：scale datatype 逐笔独立携带

每侧独立 in_scale_a_datatype/in_scale_b_datatype，每个请求的全部同侧槽共用一个类型。支持 E8M0、E4M3、E6M2 及无 scale 的 NONE；NVFP4 仍需要 E4M3，不能从接口遗漏。首版两侧格式相同，scale 类型按 [合法矩阵](interface.md) 对应，但 scale 数值可不同。S1 解包后，scale 系数/指数和控制与请求同步，不从后续输入格式取值。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 新建架构合同 | 按用户架构图及后续补充定义本模块；区分已确认结构与待审查的位宽推导，尚无实现或 EDA 证据。 | 用户确认；[流水](pipeline.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 同步本轮接口、C 解包阶段、逐请求控制或资源/验证合同；保留被替代定义。 | 用户本轮要求及确认；[总时间线](../CHANGELOG.md) |
