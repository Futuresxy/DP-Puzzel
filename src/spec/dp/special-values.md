> 功能：定义浮点分类与特殊值传播；范围：NaN/Inf/零/非正规数、scale、规约和 C 合并；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# 浮点分类、特殊值传播与 FP32 输出

状态：用户要求解包时识别 Infinity、NaN、零等，按 IEEE 754 的对应运算规则产生 FP32 结果。以下定义特殊结果的数值类别与流水传播；NaN payload、RM 编码及外部异常 flags 尚待冻结。本文件没有实现或合规验证结果。

依据为 [IEEE 754-2019](https://standards.ieee.org/ieee/754/6210/)；实现行为参考 [Berkeley HardFloat Release 1](https://www.jhauser.us/arithmetic/HardFloat-1/doc/HardFloat-Verilog.html) 的分类、异常和 NaN 定制接口。当前不引入 HardFloat/SoftFloat 依赖。

## 解包阶段分类

~~S1 必须在恢复 hidden bit、指数重编码和 E 路径定点融合前，识别每个活动 A/B 元素及 FP32 C 的类别与符号。分类保留至结果选择，不将 NaN/Inf 当作有限大数参与 MAX/移位/普通尾数规约。需要时携带 NaN 的来源/payload，具体宽度依输出策略冻结。~~

**v1.2 当前定义：** S1 对活动 A/B 与 scale 分类，再恢复 hidden bit、指数重编码及 E 定点融合；C 在 S5 才按本笔 c_datatype 分类/解包。INT32 C 不使用浮点分类。NaN/Inf 走旁带，S6 用真实 zero/special 屏蔽 MAX，S7 合并 C 摘要，S8 选择结果；分类不跨请求污染。

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

~~尚需冻结：支持的 RM 集合与默认值；NaN 使用统一 canonical qNaN 还是确定的 payload 传播顺序；invalid/overflow/underflow/inexact 是否对外输出，以及 underflow 的 tininess 判定时点。~~

**v1.1 当前定义：** 首版最终 FP32 已确定为 RNE；两次局部/全局对齐是幅值 RTZ。尚需冻结 NaN canonical/payload、IEEE 零符号细节、外部 flags 和 tininess；INT32 回绕及其验证溢出记录独立于浮点例外。若不导出 flags，合规声明必须明确接口范围，不能宣称完整 IEEE 异常环境已经实现。

本项目的分组点积使用明确的有限保留窗口。特殊值与 FP32 编码/舍入规则的符合性，以及有限数点积相对精确数学和的误差，须分别验收；前者不能证明整个点积已经做到无限精度求和后一次正确舍入。

## 验收场景

~~共用验证须覆盖分类边界、qNaN/sNaN、任意符号的 0×Inf、同/异号 Inf 相加相乘、不同 lane/不同基本组中的正负 Inf、特殊 C、特殊 scale 及无特殊编码格式的最大有限值。还包括 subnormal、负零、强抵消、normal/subnormal 边界和溢出舍入，以及 NaN/Inf 末请求、输入 bubble、排空中复位。无有效事务的保留位与未使用槽不产生异常。~~

**v1.2 当前定义：** 共用验证须覆盖分类边界、qNaN/sNaN、0×Inf、跨 lane/组的正负 Inf、特殊 C/scale、subnormal、负零、抵消、RNE 边界；加入连续 FP32/INT32 C 类型切换、NaN 请求后正常/整数请求、last 后换型、bubble 和在途复位。无效请求/槽不产生例外。

## v1.2.1：最终结果 mux 与指数安全

仅 finite_nonzero 源参与数值 LZD/MAX，zero/NaN/Inf 不以数值 sentinel 参与减 bias 或计算差值。全零有限集合以独立 numeric_active=false 标识，安全 anchor 占位为零；clz(0) 不可当作普通规格化计数使用。即使未来采用 [组 LZD 候选](group-normalization-options.md)，特殊摘要仍走原来的同延迟旁带。

S8 的结果选择顺序按当前请求类别定义：

| 条件 | 输出选择 |
| --- | --- |
| INT8 请求 | 精确整数路径的 INT32 回绕，忽略其他请求的浮点分类 |
| 浮点 has_nan 或 invalid；包括规约中同时有正负 Inf | qNaN；记录 invalid 原因，canonical/payload 策略仍待冻结 |
| 浮点仅有 has_pos_inf 或仅有 has_neg_inf | 对应符号的 Inf |
| 浮点没有上述特殊结果 | 有限 SOP+C 经过 S8 RNE/norm/pack 的 FP32 结果 |

0×Inf、相反符号 Inf 求和及 scale 运算引出的 invalid 要在各自运算节点累计；最终 mux 无法从普通 SOP 反推出这些事件。只在解包看到 NaN/Inf 时设置标记仍不足以覆盖运算新产生的 invalid。有效浮点有限结果最终溢出也可能打包为 Inf，但不能在组间抵消发生前把内部有限数过早改成 Inf。

每个请求的特殊摘要、datatype、valid、last 同步到 S8，特殊值不提前输出。无偏 anchor、scale 修正、LZD 修正、MAX 差值和最终指数都按各自范围扩宽；截回接口宽前检查可表示性，不依赖模回绕。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](../document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 更新相关数值/接口/流水定义，旧稿保留删除线。 | 用户架构图与补充；[总时间线](../CHANGELOG.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 同步本轮接口、C 解包阶段、逐请求控制或资源/验证合同；保留被替代定义。 | 用户本轮要求及确认；[总时间线](../CHANGELOG.md) |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 讨论/说明补充 | 记录组实际指数候选及对应数值、特殊值或资源边界；不改变 v1.2 主路径。 | 用户 LZD/指数/特殊值讨论；[总时间线](../CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 版本承接 | 承接v1.3架构号；正文合同及未决状态保持。 | 用户最终双向移位选择；[总时间线](../CHANGELOG.md) |
