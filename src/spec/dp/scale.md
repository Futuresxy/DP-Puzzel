> 功能：定义 scale 统一解包和 bias 处理；范围：E8M0/E4M3/E6M2 到 E8M3、组内融合及统一指数坐标；版本：v1.4.4；修改时间：2026-11-05 11:20:02 +08:00；对应代码：[CModel lib/group.cpp](../../cmodel/lib/group.cpp)；分组主方案手写 RTL：[dp_top.v](../../verilog/top/dp_top.v)；Chisel 尚未实现。

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

每个基本组已经接收按原量化块广播的 A/B scale。局部乘积先按基本组公共元素 anchor 对齐并求和；HiF4 e1 在 S1 融入元素幅值、e2 在 S3 完成局部对齐。S5 对基本组部分和乘 A/B 的 scale 系数积，再输出 sign/magnitude 组 token。

MX 的 E8M0 系数积恒为 64，解释为 I2F6 即 1.0，省去数据乘法，只把 scale 指数计入 anchor。NVFP4/HiF4 需要系数乘法。scale 为零或 NaN 时仍按特殊值合同处理；不能用零系数屏蔽非法 0×Inf。

## 3. bias 的唯一去除位置

用语义公式约束各段，令 r 为 S2 得到的基本组公共元素原始指数和：

```text
alpha_group = r - element_bias_a - element_bias_b
              + scale_exp_a + scale_exp_b - 2*scale_common_bias
value_group = signed_coefficient × 2^(alpha_group - F_group)
```

T/BF16 元素 bias 为 127，FP16 为 15，Q 在重编码后统一为 15，E 定点元素 bias 为 0；HiF4 的 r 是两侧剩余 e2 的和及其组公共最大值。INT8 无浮点 bias。

S2 可以保留原始指数和，在 S3–S5 的独立标量路径预先减去 scale 双偏置、形成元素双偏置修正；最迟在 S6 与 C 比较前完成。S8 只根据最终无偏指数编码 FP32 并加一次输出 bias，不能再次扣除已处理的元素/scale bias。

CModel 在 S5 形成已去 bias 的 A_raw，S6 直接比较统一坐标。后续 RTL 可在 S3–S5 并行提前准备固定修正，但必须保持 S5 token 数值不变。

## 4. scale datatype 逐笔独立携带

每侧独立 in_scale_a_datatype/in_scale_b_datatype，每个请求的全部同侧槽共用一个类型。支持 E8M0、E4M3、E6M2 及无 scale 的 NONE；NVFP4 仍需要 E4M3，不能从接口遗漏。首版两侧格式相同，scale 类型按 [合法矩阵](interface.md) 对应，但 scale 数值可不同。S1 解包后，scale 系数/指数和控制与请求同步，不从后续输入格式取值。

## 5. 去 bias、MAX 与 unsigned 差值

S5 组 token 的 A 已完成元素/scale bias 与定点坐标修正，C 的 A_c 同样无偏。先对有限非零源做 signed MAX，再在足够宽的 signed 临时量中计算 MAX-anchor，确认非负后转 unsigned 移位量；不能用 unsigned 比较负的无偏指数。S2/S3 的同格式产品相减中，相同的元素双 bias 抵消，因此可以保留 r/p 的带偏置无符号表示。

scale 后 LZD 只计数 z；e=A_raw-z 用于比较，d=MAX(e)-e 非负，但 net=z-d 有符号。已选 [一次双向移位](group-normalization-options.md) 为当前首选；bias 不重复扣除。

## 6. 当前资源：统一 signed15 × positive signed9

用户要求保留完整共享高位宽乘法，不再按 NVFP4/HiF4 分别缩位后输入 mux。每组一套 signed SOP × 非负系数乘法，两种模式使用同一物理输入宽度；仅允许单位系数模式的旁路/使能控制，不增加 13×9 / 15×7 格式专用压缩选择。

W_group 位组和统一精确去除 W_group−15 个结构低零，默认 W32 去除 17 位，得到 W15 TC SOP。NVFP4 的 F=4，HiF4 的 F=6。统一 scale coefficient 为 U8/F6，补一个恒零符号位进入 W9。原生乘积 W24，其最高位在合法非负系数范围内为冗余符号扩展；公共检查后取 signed W23，低补 W_group−23 个零回组槽，默认补 9 个零。默认 NVFP4/HiF4 的原幅值分别为 F19/F21，其中末尾 9 位是结构低零。

| 模式 | 同一 SOP 输入 | 同一 scale 输入 | 公共有用乘积 | 原生 W24 乘积 | 默认 W32 落位 |
| --- | --- | --- | --- | --- | --- |
| NVFP4 | TC S1I10F4 W15 | 正 TC S1I2F6 W9 | TC S1I12F10 W23 | TC S1I13F10 | 补 9 零，S1I12F19 |
| HiF4 | TC S1I8F6 W15 | 正 TC S1I2F6 W9 | TC S1I10F12 W23 | TC S1I11F12 | 补 9 零，S1I10F21 |

```text
W_sop_shared = E_pair_signed_width + e_exact_guard_bits
               + ceil_log2(E_pairs_per_lane) + ceil_log2(lanes_per_group)
W_factor_unsigned = 2*scale_magnitude_bits
W_factor_signed = W_factor_unsigned+1
W_product_native = W_sop_shared+W_factor_signed
W_product_useful = W_sop_shared+W_factor_unsigned
sop_low_drop = W_group-W_sop_shared
product_low_pad = W_group-W_product_useful
F_group_scaled = F_group_unscaled-sop_low_drop + 2*scale_fraction_bits + product_low_pad
```

两模式均不去掉各自额外的结构零。相同的 low-drop 和 high-sign 检查属于公共精确表示变换，不是新的精度截断。CModel 对整除及乘积有符号范围断言，trace 记录 15/9/24/23。乘法后才 abs/LZD，S5 不左移；S6 仍按 z-d 一次双向移位。

用户反馈缩位 mux 的面积收益不足，因此当前按完整资源建模；本仓库本轮无对应新 RTL/EDA 数据，不把该反馈转换为本项目实测面积、功耗或时序结论。

## 7. 主要版本变更：v1.3 → v1.4

~~分别压缩 NV 的 SOP 与 HiF 的 scale 系数，再由格式 mux 接入共享乘法器。~~ → **统一 15×9 输入，不增加模式专用缩位 mux。** 公共 W24→W23 冗余符号处理与静态低零落位保持精确。变更依据为用户对资源设计的最新选择。
