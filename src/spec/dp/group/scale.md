> 功能：定义 scale 统一解包和 bias 处理；范围：E8M0/E4M3/E6M2 到 E8M3、组内融合及统一指数坐标；版本：v1.5.5；修改时间：2026-11-06 13:54:29 +08:00；对应代码：[CModel lib/group.cpp](../../../cmodel/lib/group.cpp)、[dp_group.v](../../../verilog/group/dp_group.v)、[dp_scale_multiply.v](../../../verilog/arithmetic/dp_scale_multiply.v)；Chisel 尚未实现。

# scale 统一 E8M3 数值表示

状态：用户确定三种 scale 统一成 8 位指数 + I1F3 幅值的内部表示；S1 解包，S2 并行形成指数和及 4×4 系数积，S5 对需要的路径应用系数。内部 E8M3 是字段记录，不是新的外部 IEEE 编码。

## 1. 单侧 scale

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

NVFP4 的 scale 采用非负 E4M3：bit7=0 为合法输入约束，负 scale 属于 payload 违规，由源保证并由验证器报错，不能静默忽略 bit7。额外 per-tensor scale 不自动添加到本 DP 接口；若需要由上层折入 C/D 之外的缩放或另提明确合同。

bias 和字段宽度集中在格式参数中。8 位指数相加产生 9 位结果，4 位系数相乘产生 8 位 coefficient，小数位为 6；这些结果不能截回输入宽度。

## 2. 应用顺序与旁路

每个基本组已经接收按原量化块广播的 A/B scale。局部乘积先按基本组公共元素 anchor 对齐并求和；HiF4 e1 在 S1 融入元素幅值、e2 在 S3 完成局部对齐。S5 合并两 lane 的有符号部分和，再分离符号与幅值。NVFP4/HiF4 对幅值乘 A/B 的 scale 系数积，其他模式旁路系数乘法。

MX 的 E8M0 系数积恒为 64，解释为 I2F6 即 1.0，省去数据乘法，只把 scale 指数计入 anchor。NVFP4/HiF4 需要系数乘法。scale 为零或 NaN 时仍按特殊值合同处理；不能用零系数屏蔽非法 0×Inf。

## 3. bias 的唯一去除位置

用语义公式约束各段，令 r 为 S2 得到的基本组公共元素原始指数和：

```text
alpha_group = r - element_bias_a - element_bias_b
              + scale_exp_a + scale_exp_b - 2*scale_common_bias
value_group = (-1)^sign × magnitude × 2^(alpha_group - F_group)
```

T/BF16 元素 bias 为 127，FP16 为 15，Q 在重编码后统一为 15，E 定点元素 bias 为 0；HiF4 的 r 是两侧剩余 e2 的和及其组公共最大值。INT8 无浮点 bias。

S2 可以保留原始指数和，在 S3–S5 的独立标量路径预先减去 scale 双偏置、形成元素双偏置修正；最迟在 S6 与 C 比较前完成。S8 只根据最终无偏指数编码 FP32 并加一次输出 bias，不能再次扣除已处理的元素/scale bias。

CModel 在 S5 形成已去 bias 的 A_raw，S6 直接比较统一坐标。后续 RTL 可在 S3–S5 并行提前准备固定修正，但必须保持 S5 token 数值不变。

## 4. scale datatype 逐笔独立携带

每侧独立 in_scale_a_datatype/in_scale_b_datatype，每个请求的全部同侧槽共用一个类型。支持 E8M0、E4M3、E6M2 及无 scale 的 NONE；NVFP4 仍需要 E4M3，不能从接口遗漏。首版两侧格式相同，scale 类型按 [合法矩阵](../dptop/interface.md) 对应，但 scale 数值可不同。S1 解包后，scale 系数/指数和控制与请求同步，不从后续输入格式取值。

## 5. 去 bias、MAX 与净移位

S5 组 token 的 A 已完成元素/scale bias 与定点坐标修正，C 的 A_c 同样无偏。先对有限非零源的实际指数做 signed MAX。右对齐距离 d 为非负数，合并规格化后的净移位 net 用带符号差值计算。S2/S3 的同格式乘积指数相减中，相同的元素双 bias 抵消，因此可以保留 r/p 的带偏置无符号表示。

scale 后 LZD 只计数 z；e=A_raw-z 用于比较，d=MAX(e)-e 非负，但 net=z-d 有符号。已选 [一次双向移位](../dptop/global-align.md) 为当前首选；bias 不重复扣除。

## 6. S5 共享 14×8 无符号乘法

组树的两路输入及输出仍为二补码。乘法与旁路共享组和的符号提取和绝对值。NVFP4/HiF4 从绝对值去除 `W_group−15` 个结构低零。默认 W32 去除 17 个低零。两种模式共用同一条 14 位幅值输入及 8 位非负系数输入。其他模式使用完整组幅值旁路，符号独立随组 token 传递。

紧凑组和可以用 14 位幅值表示。NVFP4 的单元素幅值 coefficient 最大为 12，HiF4 融合 e1 后最大为 14。一个基本组有 16 个乘积，预置两位保护低零贡献最多 4 倍 coefficient，局部右移只会减小幅值。故紧凑组和绝对值上界分别为 `16×12²×4=9216` 与 `16×14²×4=12544`，均小于 `2^14`。取绝对值时应以足够宽的中间值检查合法范围，随后装入公共 14 位无符号槽。

| 模式 | 紧凑组和（TC） | 乘法器幅值输入 | 系数输入 | 22 位无符号乘积 | 默认 M31 幅值槽 |
| --- | --- | --- | --- | --- | --- |
| NVFP4 | S1I10F4 | S0I10F4 | S0I2F6 | S0I12F10 | 低补 9 零，S0I12F19 |
| HiF4 | S1I8F6 | S0I8F6 | S0I2F6 | S0I10F12 | 低补 9 零，S0I10F21 |

```text
W_sop_tc = E_pair_signed_width + e_exact_guard_bits
           + ceil(log2(E_pairs_per_lane)) + ceil(log2(lanes_per_group))
W_sop_magnitude = W_sop_tc - 1
W_factor = 2 * scale_magnitude_bits
W_product = W_sop_magnitude + W_factor
sop_low_drop = W_group - W_sop_tc
product_low_pad = M_group - W_product
F_group_scaled = F_group_unscaled - sop_low_drop + 2*scale_fraction_bits + product_low_pad
```

乘积静态补零后送 LZD，S5 只输出计数 z 和原始幅值。负号及零符号按原组和与特殊值规则传递，包括负组和乘零系数的情况。S6 对无符号幅值进行一次双向移位，在进入 S7 有符号累加树前恢复二补码。

## 7. 主要版本变更（v1.4 → v1.5）

~~组和经过 15×9 有符号乘法，随后取乘积幅值。~~ → **组和先分离符号与幅值，幅值经过 14×8 无符号乘法。** 对非负系数有 `abs(sop × coeff) = abs(sop) × coeff`，原有 F、补零、截断位置和 L8/II=1 由 [v1.5.1 功能回归](../../../../test/results/verilog-v1.4.md) 核对。
