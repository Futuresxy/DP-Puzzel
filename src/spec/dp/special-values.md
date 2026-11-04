# 浮点分类、特殊值传播与 FP32 输出

状态：用户要求解包时识别 Infinity、NaN、零等，按 IEEE 754 的对应运算规则产生 FP32 结果。以下定义特殊结果的数值类别与流水传播；NaN payload、RM 编码及外部异常 flags 尚待冻结。本文件没有实现或合规验证结果。

依据为 [IEEE 754-2019](https://standards.ieee.org/ieee/754/6210/)；实现行为参考 [Berkeley HardFloat Release 1](https://www.jhauser.us/arithmetic/HardFloat-1/doc/HardFloat-Verilog.html) 的分类、异常和 NaN 定制接口。当前不引入 HardFloat/SoftFloat 依赖。

## 解包阶段分类

S1 必须在恢复 hidden bit、指数重编码和 E 路径定点融合前，识别每个活动 A/B 元素及 FP32 C 的类别与符号。分类保留至结果选择，不将 NaN/Inf 当作有限大数参与 MAX/移位/普通尾数规约。需要时携带 NaN 的来源/payload，具体宽度依输出策略冻结。

FP16、BF16、TF32、FP32 C 按各自字段识别 ±0、有限非正规数、有限正规数、±Inf 和 NaN；支持信号/静默 NaN 的格式继续区分 sNaN/qNaN。正常与非正规输入都进入有限数路径；IEEE 行为目标包含渐进下溢，不默认启用输入 denormals-are-zero 或输出 flush-to-zero。

MX 子格式按其自身编码分类，不能统一以“指数全 1”判断无穷或 NaN。按 [OCP MX v1.0 §5.3](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)，E4M3 不编码 Inf，E5M2 可编码 Inf/NaN，FP6 和 E2M1 不预留 Inf/NaN。块 scale 的 NaN/保留编码需按 scale 合同处理。HiF4 S1P2 元素为有限定点数，没有 Inf/NaN 编码；E6M2 块 scale 的 0xff 为 NaN、其余非零有限，具体公式见解包合同。

## 单项乘法与加法规则

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

## 分组规约、scale 与 C 合并

各层随部分和传递足以恢复特殊结果的摘要，例如 `has_nan`、`invalid`、`has_pos_inf`、`has_neg_inf`，以及必要的零符号/NaN 信息。字段是语义要求，具体模块边界待 RTL 映射确定。

1. 局部乘法依据原始类别生成特殊乘积，有限乘积使用 E/M/S 运算。
2. lane、基本组及跨组规约合并特殊摘要：任意 invalid 或 NaN 导向 qNaN；求和中同时出现正负 Inf 产生 invalid/qNaN；仅一种符号的 Inf 则保持该 Inf。
3. scale 只能按已经明确的计算顺序应用。若 scale 格式允许零、Inf 或 NaN，分别遵循相应乘法规则；不能将 scale 解码为整数指数后丢失其特殊编码。各层 scale 的确切施加位置仍由格式合同冻结。
4. S7 将缩放点积摘要与 C 分类合并：例如点积 +Inf 与 C=-Inf 得到 qNaN；有限点积与 C=+Inf 得到 +Inf；任何非法乘积不会因 C 为 Inf 或 qNaN 被视为正常。
5. S8 选择 qNaN、带符号 Inf 或有限路径 FP32 编码；特殊结果也遵循完整模式延迟及对应 valid/last。

有限部分和不因超过 FP32 范围就提前改为 Inf。内部指数范围与保留位宽须支撑规定操作，避免可被后续组或 C 抵消的中间值过早溢出。最终有限数溢出后的 Inf/最大有限数选择由 RM 定义。

## 零、非正规数、舍入与异常

精确抵消为零、多个带符号零求和以及微小值舍入至零的符号需依运算及 RM 规则定义，不能统一清除 sign。输入非正规数的 h 和有效指数按 [解包合同](unpack.md) 处理；FP32 输出在正常数/非正规数边界正确舍入，避免误把 tiny 等同于必定 underflow/inexact。

尚需冻结：支持的 RM 集合与默认值；NaN 使用统一 canonical qNaN 还是确定的 payload 传播顺序；invalid/overflow/underflow/inexact 是否对外输出，以及 underflow 的 tininess 判定时点。若不导出 flags，合规声明必须明确接口范围，不能宣称完整 IEEE 异常环境已经实现。

本项目的分组点积使用明确的有限保留窗口。特殊值与 FP32 编码/舍入规则的符合性，以及有限数点积相对精确数学和的误差，须分别验收；前者不能证明整个点积已经做到无限精度求和后一次正确舍入。

## 验收场景

共用验证须覆盖分类边界、qNaN/sNaN、任意符号的 0×Inf、同/异号 Inf 相加相乘、不同 lane/不同基本组中的正负 Inf、特殊 C、特殊 scale 及无特殊编码格式的最大有限值。还包括 subnormal、负零、强抵消、normal/subnormal 边界和溢出舍入，以及 NaN/Inf 末请求、输入 bubble、排空中复位。无有效事务的保留位与未使用槽不产生异常。
