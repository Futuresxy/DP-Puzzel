> 功能：定义浮点分类与特殊值传播；范围：NaN/Inf/零/非正规数、scale、规约和 C 合并；版本：v1.4.2；修改时间：2026-11-04 23:42:09 +08:00；对应代码：[CModel lib/arithmetic.cpp](../../cmodel/lib/arithmetic.cpp)；分组主方案手写 RTL：[dp_top.v](../../verilog/top/dp_top.v)；Chisel 尚未实现。

# 浮点分类、特殊值传播与 FP32 输出

首版特殊值策略已由用户确认，见 [CModel 合同](cmodel.md)：canonical qNaN、RNE 零符号、渐进下溢及舍入后 tininess；异常只记录验证 trace。实现验证不等于完整 IEEE 环境合规或无限精度点积一次正确舍入。

依据为 [IEEE 754-2019](https://standards.ieee.org/ieee/754/6210/)；实现行为参考 [Berkeley HardFloat Release 1](https://www.jhauser.us/arithmetic/HardFloat-1/doc/HardFloat-Verilog.html) 的分类、异常和 NaN 定制接口。当前不引入 HardFloat/SoftFloat 依赖。

## 1. 解包阶段分类

S1 对活动 A/B 与 scale 分类，再恢复 hidden bit、指数重编码及 E 定点融合；C 在 S5 才按本笔 c_datatype 分类/解包。INT32 C 不使用浮点分类。NaN/Inf 走旁带，S6 用真实 zero/special 屏蔽 MAX，S7 合并 C 摘要，S8 选择结果；分类不跨请求污染。

FP16、BF16、TF32、FP32 C 按各自字段识别 ±0、有限非正规数、有限正规数、±Inf 和 NaN；支持信号/静默 NaN 的格式继续区分 sNaN/qNaN。正常与非正规输入都进入有限数路径；IEEE 行为目标包含渐进下溢，不默认启用输入 denormals-are-zero 或输出 flush-to-zero。

MX 子格式按其自身编码分类，不能统一以“指数全 1”判断无穷或 NaN。按 [OCP MX v1.0 §5.3](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)，E4M3 不编码 Inf，E5M2 可编码 Inf/NaN，FP6 和 E2M1 不预留 Inf/NaN。块 scale 的 NaN/保留编码需按 scale 合同处理。HiF4 S1P2 元素为有限定点数，没有 Inf/NaN 编码；E6M2 块 scale 的 0xff 为 NaN、其余非零有限，具体公式见解包合同。

## 2. 单项乘法与加法规则

下表先描述无其他 NaN 输入时的类别结果；所有局部 invalid 条件均需保留，不因另一路已有 qNaN 被错误清除。

| 运算情况 | 结果类别 |
| --- | --- |
| sNaN 参与运算 | quiet NaN，产生 invalid 条件 |
| qNaN 参与运算 | quiet NaN；其自身不产生 invalid |
| `0 × Inf` 或 `Inf × 0`，任意符号 | quiet NaN，invalid |
| `Inf × 有限非零值` 或 `Inf × Inf` | Inf，符号为两个符号 XOR |
| `+Inf × -Inf` | `-Inf`，不因符号相反而 invalid |
| `±0 × 有限值` | 零，符号为两个符号 XOR |
| `+Inf + -Inf` | quiet NaN，invalid |
| 同号 `Inf + Inf` | 同号 Inf |
| `Inf + 有限值` | 该 Inf |
| 有限值相加/乘 | 进入已定义有限位宽路径，最后按 RM 输出 |

本 DP 不含除法。Inf 作为结果并不意味着发生 divide-by-zero，不能直接用 `is_inf` 生成异常 flags。NaN 与 invalid 的区分也需要保留。

## 3. 分组规约、scale 与 C 合并

各层随部分和传递足以恢复特殊结果的摘要，例如 `has_nan`、`invalid`、`has_pos_inf`、`has_neg_inf`，以及必要的零符号/NaN 信息。字段是语义要求，具体模块边界待 RTL 映射确定。

1. 局部乘法依据原始类别生成特殊乘积，有限乘积使用 E/M/S 运算。
2. lane、基本组及跨组规约合并特殊摘要：任意 invalid 或 NaN 导向 qNaN；求和中同时出现正负 Inf 产生 invalid/qNaN；仅一种符号的 Inf 则保持该 Inf。
3. scale 只能按已经明确的计算顺序应用。若 scale 格式允许零、Inf 或 NaN，分别遵循相应乘法规则；不能将 scale 解码为整数指数后丢失其特殊编码。scale 施加位置由[scale 合同](scale.md)规定。
4. S7 将缩放点积摘要与 C 分类合并：例如点积 +Inf 与 C=-Inf 得到 qNaN；有限点积与 C=+Inf 得到 +Inf；任何非法乘积不会因 C 为 Inf 或 qNaN 被视为正常。
5. S8 选择 qNaN、带符号 Inf 或有限路径 FP32 编码；特殊结果也遵循完整模式延迟及对应 valid/last。

有限部分和不因超过 FP32 范围就提前改为 Inf。内部指数范围与保留位宽须支撑规定操作，避免可被后续组或 C 抵消的中间值过早溢出。最终有限数溢出后的 Inf/最大有限数选择由 RM 定义。

## 4. 零、非正规数、舍入与异常

精确抵消为零、多个带符号零求和以及微小值舍入至零的符号需依运算及 RM 规则定义，不能统一清除 sign。输入非正规数的 h 和有效指数按 [解包合同](unpack.md) 处理；FP32 输出在正常数/非正规数边界正确舍入，避免误把 tiny 等同于必定 underflow/inexact。

首版特殊值策略已由用户确认，见 [CModel 合同](cmodel.md)：canonical qNaN、RNE 零符号、渐进下溢及舍入后 tininess；异常只记录验证 trace。实现验证不等于完整 IEEE 环境合规或无限精度点积一次正确舍入。

本项目的分组点积使用明确的有限保留窗口。特殊值与 FP32 编码/舍入规则的符合性，以及有限数点积相对精确数学和的误差，须分别验收；前者不能证明整个点积已经做到无限精度求和后一次正确舍入。

## 5. 验收场景

共用验证须覆盖分类边界、qNaN/sNaN、0×Inf、跨 lane/组的正负 Inf、特殊 C/scale、subnormal、负零、抵消、RNE 边界；加入连续 FP32/INT32 C 类型切换、NaN 请求后正常/整数请求、last 后换型、bubble 和在途复位。无效请求/槽不产生例外。

## 6. 最终结果 mux 与指数安全

仅 finite_nonzero 源参与数值 LZD/MAX，zero/NaN/Inf 不以数值 sentinel 参与减 bias 或计算差值。全零有限集合以独立 numeric_active=false 标识，安全 anchor 占位为零；clz(0) 不可当作普通规格化计数使用。当前[组 LZD 与合并对齐](group-normalization-options.md)同样保留特殊摘要的等延迟旁带。

S8 的结果选择顺序按当前请求类别定义：

| 条件 | 输出选择 |
| --- | --- |
| INT8 请求 | 精确整数路径的 INT32 回绕，忽略其他请求的浮点分类 |
| 浮点 has_nan 或 invalid（v1.4） | canonical qNaN=0x7fc00000；记录 invalid |
| 浮点仅有 has_pos_inf 或仅有 has_neg_inf | 对应符号的 Inf |
| 浮点没有上述特殊结果 | 有限 SOP+C 经过 S8 RNE/norm/pack 的 FP32 结果 |

0×Inf、相反符号 Inf 求和及 scale 运算引出的 invalid 要在各自运算节点累计；最终 mux 无法从普通 SOP 反推出这些事件。只在解包看到 NaN/Inf 时设置标记仍不足以覆盖运算新产生的 invalid。有效浮点有限结果最终溢出也可能打包为 Inf，但不能在组间抵消发生前把内部有限数过早改成 Inf。

每个请求的特殊摘要、datatype、valid、last 同步到 S8，特殊值不提前输出。无偏 anchor、scale 修正、LZD 修正、MAX 差值和最终指数都按各自范围扩宽；截回接口宽前检查可表示性，不依赖模回绕。

## 7. 首版已确认策略

所有 NaN 输出统一 `0x7fc00000`，不传播 payload；原格式支持 sNaN 时按最高 fraction 位识别，触发 invalid。E4M3、E8M0、HiF E6M2 的专用 NaN 没有 sNaN 变体。无除法及 divide-by-zero 标志。

RNE 下精确非零相消为 +0；仅当所有参与相加的零项均为负零时保留 −0。非零微小负值最终舍入为零保留负号。局部/全局 magnitude RTZ 到零保留该项符号，再按同一零和规则规约。输入非正规不冲零，输出渐进下溢。

invalid 汇总 sNaN、0×Inf、异号 Inf 规约等；overflow/inexact/underflow 描述 S8 对规定有限位宽总和的转换。tininess 在舍入后判断，只有结果仍小于最小正规且 inexact 才置 underflow。S3/S6 丢位独立记录 local_truncated/global_truncated，不把丢失值补回 S8，也不将这两个记录冒充整个理想点积的 IEEE flags。integer_overflow 独立记录回绕前越界。

这些 flags 是 CModel/验证诊断，未增加 DUT 输出端口。NaN/Inf 最终 mux 优先于有限数转换，不因被屏蔽的数值支路溢出而产生 S8 overflow。

## 8. 主要版本变更：v1.3 → v1.4

~~NaN 编码、零符号细节及 tininess 策略待冻结。~~ → **采用 canonical qNaN、RNE 零符号、渐进下溢和舍入后 tininess，异常仅记 trace。** 依据为用户首版策略确认。
