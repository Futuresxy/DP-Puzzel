> 功能：推导逐级位宽和统一对齐坐标；范围：参数化局部/全局窗口、sign/magnitude、S5 C 和 INT32；版本：v1.4.2；修改时间：2026-11-04 23:42:09 +08:00；对应代码：[CModel lib/group.cpp](../../cmodel/lib/group.cpp)；分组主方案手写 RTL：[dp_top.v](../../verilog/top/dp_top.v)；Chisel 尚未实现。

# 逐级位宽、符号/幅值与 anchor

状态：用户确定两次移位均对无符号幅值向零截断，S5 T2H4Q8E16 输出独立符号/幅值；宽度和树深由参数派生。以下为与图一致的可审阅数值推导，不代表完整误差或时序验收。

## 1. 集中参数与自然增长

所有结构值由有效配置进入 Chisel 参数对象及模块构造参数；计划入口 `src/chisel/parameter/`，文件尚未创建。CModel、手写 Verilog 与 TB 使用同一有效参数，不从各模块中的常数字面值拼装设计。

```text
L(n) = ceil(log2(n)), L(1)=0
product_width = operand_width_a + operand_width_b
sum_signed_width(w,n) = w + L(n)
local_mag_width = product_integer_bits + local_align_fraction_bits
local_signed_width = local_mag_width + 1
pair_count_E = elements_per_lane_E / 2
hif_delta_max = operands_per_product * (2^hif_e2_bits - 1)
e_exact_guard_bits = hif_delta_max
E_pair_signed_width = 2*e_magnitude_bits + 1 + L(2)
E_group_compact_width = E_pair_signed_width + e_exact_guard_bits
                        + L(pair_count_E) + L(lanes_per_base_group)
```

本配置 `local_align_fraction_bits=25`、乘积整数位=2，得到无符号 W27=I2F25、符号化后 W28。E 元素幅值四位、e2 一位、两侧相乘，推导 pair W10、guard=2、四个 pair 的 lane 和 W14、两个 lane 的基本组和 W15；15 已含符号，不能将它当作任意模式的统一精度常量。

对 n 个叶节点的平衡树，由参数生成每层两两相加，未配对叶节点直传，层数 L(n)；各节点按输入宽度与增长推导。顶层参与数为 `group_count+1`（包括 C），K4/K8/K16 对应 2/3/5 项，树深 1/2/3；三组或其他未来非二次幂也遵循该规则，但当前合法构建 K 仍为 4/8/16。

## 2. S2 到 S3：T/H/Q 初次对齐

| 模式 | 原始无符号幅值乘积 | 原小数位 | 放入 I2F25 的低位补零 |
| --- | --- | --- | --- |
| TF32/FP16 | W22，I2F20 | 20 | 25-20 |
| BF16 | W16，I2F14 | 14 | 25-14 |
| Q | W8，I2F6 | 6 | 25-6 |

基本组公共 r 是两个 lane 所有有效有限非零乘积指数的 MAX，delta=r-e_product。若有效有限非零乘积集合为空，参考 r 使用安全占位零、数据幅值全部为零；特殊值与零符号仍通过旁带传递。S3 对无符号幅值执行逻辑右移，`delta>=local_mag_width` 时幅值为零；随后以独立 sign XOR 转成补码供加法树使用。向零截断发生在该保留窗口，不能把负数直接算术右移后的 -1 当作小负值的正确零结果。

25 是当前小数位配置下限；派生 W27 不含符号。移出位可用于误差统计，不能未经新数值合同直接混入最终舍入；S8 RNE 对已规定有限位宽路径结果舍入，不意味着被局部截断的精确点积可恢复。

## 3. S3 到 S5：E、整数及共享加法树

E 的八个产品先两两符号化相加为四个 pair。每个 pair 低位补 `e_exact_guard_bits`，HiF4 再按基本组公共 e2 和右移 0/1/2 位，随后参与四路求和。由于所有移位前至少有两个低零，HiF4 此处精确；取差值低两位前必须先保证 delta≤2，不能把更大差值截短后回绕。

Q 四路在 S4 通过两层加法；H 两路复用最后一层；T 单项通过最后一级的旁路或与零相加，保持同一寄存边界。E 的四个 pair 和 INT8 的四个产品使用相同四路树。每种模式先按参数给出自然表示，再以**有符号值低位补零**放入共用槽；补 p 位必须同步令 F 增加 p，数值不变。

当前 CModel 采用的共享槽为：S3 补码叶 W28、S4 lane 槽 W30、S5 基本组补码槽 W31。下表 F 是该槽对应的小数点，不是新增加的数学信息：

| 模式 | S4 lane W30 的 F | S5 W31 的 F（含 scale 系数后的落位） |
| --- | ---: | ---: |
| T | 27 | 27 |
| FP16/BF16 | 26 | 26 |
| Q | 25 | 25 |
| MXFP4，单位 scale 系数 | 20 | 20 |
| NVFP4，非单位 scale 系数 | 20 | 18 |
| HiF4，非单位 scale 系数 | 22 | 20 |
| INT8，结构低零 | 12 | 12 |

S5 只检测 z，不左移，原幅值 F 保持。NV/HiF 统一 W15×W9，公共 W23 有用积补 8 零；不用每模式缩位选择。S6 合并完成规格化及对齐。

## 4. 共享槽与 F 的构造公式

```text
W_leaf = local_signed_width
W_lane = W_leaf + L(elements_per_lane_Q)
W_group = W_lane + L(lanes_per_base_group)
W_lane_natural(T/H/Q) = local_signed_width + L(elements_per_lane(mode))
F_lane_natural(T/H/Q) = local_align_fraction_bits
W_lane_natural(E) = E_pair_signed_width + e_exact_guard_bits + L(pair_count_E)
F_lane_natural(E) = e_product_fraction_bits(mode) + e_exact_guard_bits
W_lane_natural(INT8) = signed_width_from_product_range(INT8) + L(elements_per_lane_INT8)
F_lane_natural(INT8) = 0
pad_lane(mode) = W_lane - W_lane_natural(mode)
F_lane(mode) = F_lane_natural(mode) + pad_lane(mode)
F_group_unscaled(mode) = F_lane(mode)
W_scale_product = 2 * scale_mantissa_bits
F_scale_product = 2 * scale_mantissa_fraction_bits
W_compact_scaled = E_group_compact_width + W_scale_product
F_group_scaled(E) = e_product_fraction_bits(mode) + e_exact_guard_bits
                    + F_scale_product + W_group - W_compact_scaled
```

signed_width_from_product_range 从完整合法输入范围推导，包括 -128；不用浮点尾数的 sign+自然无符号宽度估计代替。所有 pad 均须非负，按模式裁剪高符号扩展或低结构零必须有范围/整除证明；不适用的公式分支不生成硬件。E8M0 单位系数旁路直接使用 F_group_unscaled，不让虚拟系数人为移动小数点。

## 5. S5：scale 后幅值与 LZD 计数

S5 完成两 lane 组和、适用 scale 乘法/旁路、安全 abs，再对最终 m_raw 求 z=clz_M(m_raw)，**只输出计数，不左移**。组幅值默认 M30，A_raw=alpha_raw-F_raw+(M-1)已去 bias；正式出口保持各模式原 F_raw。接口输出 m_raw/negative/A_raw/z/zero/special 及同行控制。e=A_raw-z 是 MAX 用的真实指数，不能单独用 e 解释未左移幅值。

C 仍 S1–S4 raw32、S5 并行解包。FP32 自然 M24 低补 8 零到 M32/F31，子正规仅检测 z_c，不左移；A_raw_c 为有效无偏指数，e_c=A_raw_c-z_c。INT32 仍 M32/F0；零/特殊源不做普通非零公式。

## 6. S6：合并左规格化与右对齐

对有限非零源求 e_i=A_raw_i-z_i 及 signed E_max；d_i=E_max-e_i 非负，净移位 net_i=z_i-d_i=A_raw_i-E_max 为 signed。原幅值先静态补到 M_global，再由一套双向移位器按 net_i 正左负右移动；右移 RTZ，之后恢复补码。公共 LSB 权重 lambda_common=E_max-(M_global-1)。零/特殊屏蔽、完整差值及过大移位处理见 [出口表](stage-formats.md)。

默认 signed 全局窗口 40、幅值 39；所有 pad 由参数推导并保证非负。左移 net_i≤z_i，故不会移出有效位。该合并与先精确左移再右移等价，不需要 S5 左移器；INT 分支仍使用可逆结构落位。S3 移位资源不与 S6 跨拍复用。

## 7. S7：一次规约所有组与 C

`N=group_count+1`，每个输入为 global_signed_align_width 位，输出自然宽度 `W_sum=global_signed_align_width+L(N)`。默认 W40 下，K4/K8/K16 的总和分别 W41/W42/W43，不把五项和截回 W40。加法树可采用平衡 CPA 或压缩树，单周期完成是目标，组合路径需评估。

总和仍位于 lambda_common。S8 对绝对值求最高有效位 k，最终无偏指数 `E=lambda_common+k`；若采用随容器最高位的 anchor 表示，宽度增长必须同步修正 anchor。不得用裸 raw anchor 直接编码 FP32。

## 8. INT8/INT32 与共用输出

有符号 INT8 输入解为符号+8 位幅值；每笔 C 根据其 INT32 datatype 解包，输出携带 INT32 datatype。S3、S6 不做浮点指数对齐，低零仅用于可逆结构落位；相邻浮点请求不会改变本笔解释。

C 的绝对值最多 2^31，故需要 32 位无符号幅值。令 `int_pad_bits=M_global-int32_bits`（默认 39-32=7），将各组整数与 C 的幅值统一低位补该数量零，再恢复符号。INT8 原始乘积虽由 16 位无符号单元产生，但合法输入范围保证乘积在 [-16256,16384]，可精确用 16 位补码；共享 W28 叶槽因此补 12 个低零，S4/S5 保持该 F。组槽中原有结构低零先按其派生 F 精确还原，不能把它们当作真实小数截断。要求 M_global≥int32_bits。

S7 保留完整求和；S8 精确删除结构零后得到数学整数 R，输出 `D_bits=R mod 2^32`，按二补码 INT32 解释。溢出条件 `R < -2^31 or R > 2^31-1` 记入验证/trace；本轮不新增 DUT 异常端口。即使 R 溢出，也不变成 NaN/Inf 或触发 RNE。

IEEE 754 的浮点转整数异常不规定本项目整数乘加的溢出选择；用户已选首版回绕。[PTX ISA 9.0 的整数 mma](https://docs.nvidia.com/cuda/archive/13.0.2/parallel-thread-execution/index.html#warp-level-matrix-instructions-mma) 同样区分未指定 satfinite 的回绕和指定后的饱和；此处不引入饱和模式。

## 9. INT32 回绕示例

- C=2147483647、点积贡献=1：数学 R=2147483648，输出位为 0x80000000，按 INT32 为 -2147483648，overflow=true。
- C=-2147483648、点积贡献=-1：数学 R=-2147483649，输出位为 0x7fffffff，按 INT32 为 2147483647，overflow=true。
- R 在 [-2^31,2^31-1] 内时数值不变，overflow=false。输出行为与 overflow 记录分开，不增加输出周期。

## 10. S8 RNE 与剩余数值待决项

首版 FP32 只支持 RNE，相等时取偶数。设规范化后保留位最低位为 lsb，丢弃部分首两位为 guard/round，其后各位 OR 为 sticky，则进位条件为 `guard && (round || sticky || lsb)`；舍入进位可再次调整输出指数。对 S7 有限结果确定符号、LZD、规范化、guard/round/sticky 及舍入进位，再打包 FP32。

NaN/零符号/tininess/trace flags 已按 [特殊值策略](special-values.md) 冻结；RNE 不追溯修复 RTZ 的信息损失。

当前已把主模式首次局部对齐解释为至少 25 个小数位。FP4 35/HiF4 37 的精度计数口径及在 W40 全局窗口下的误差边界仍需证明，不能把 40 位容器自动视为这些目标已验收。

## 11. 完整出口表与移位器主参数

[每级 SxIxFx/anchor/SOP](stage-formats.md) 展开默认参数全部格式的 S1–S8 出口。局部窗口的唯一主配置为 local_shift_mag_width，默认 27；local_align_fraction_bits=local_shift_mag_width-product_integer_bits 为派生量，当前要求至少 25。原 local_mag_width 公式仍成立，但不允许再单独输入一份矛盾的 F。S3 的实际四个移位器经输入 mux 在 T/H/Q 间共享，见 [资源合同](shifter-sharing.md)。

S5 改传 anchor_raw=A_raw、z 及未左移 M30 幅值；S6 计算 e/MAX，按 z-d 一次双向移位。S6/S7 仍 W40/W43、F38，公共指数为实际 e 的 MAX；INT 坐标不变。

## 12. 容器 anchor 与实际指数

已选择 [scale 后计数＋合并双向移位](group-normalization-options.md)。S6 结果应与精确双单向方案一致。

## 13. 宽度公式的适用范围

采用公共 W_compact_scaled=E_group_compact_width+W_scale_product，即有用 W23；signed×positive-signed 原生 W24 的最高冗余符号位按范围检查处理。S5 F 与 LZD 计数含义不变，见 [scale](scale.md)。
