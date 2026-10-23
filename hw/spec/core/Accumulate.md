# Accumulate.scala：共享 C/D 数据通路

对应源码：[Accumulate.scala](../../chisel_src/core/Accumulate.scala)。这是在 MNPE/KPE 内展开的公共电路构建函数，不是额外的计算组织 Module；只实例化基础 `Fp32Pack`。

功能是 `D = sum(dots) + C`。MNPE 传入一个 dot，KPE 传入 1–4 个 dot，并在调用前屏蔽当前模式不支持的 PE。只加一次 C、只做一次最终归一化/舍入；不会先把各 PE 舍入成 FP32 再相加，避免额外中间舍入与 C 重复计入。

## 位宽与时序

参数 width 必须等于每个 DotResult 的公共位宽，默认 42。dots 在 S11 可用，control/inputValid 从 S0 进入；此函数不能作为“任意时间到达”的独立接口使用。

| 级 | dot/C/控制处理 |
| --- | --- |
| S1–S9 | C 原始 32-bit 与 C format 延迟，避免早期存储宽解码状态 |
| S10 | FP32/FP16/BF16 C 解包为 W24 magnitude + sign |
| S11 | C 无损 LZD 规格化，与 PE dot 同拍；低位补零匹配公共小数点 |
| S12 | 所有非零项做 MAX，存 terms、winner、饱和 shift、anchor |
| S13 | MAX 旁路，其他项 unsigned magnitude 右移后加符号（RTZ） |
| S14 | CSA + CPA 对 dot 和 C 求和 |
| S15–S16 | 绝对值/LZD、归一化和 guard/sticky 提取 |
| S17–S18 | Fp32Pack 最终舍入与打包 |

项数 N=dotCount+1，因此可能为 2/3/4/5；sumWidth=width+ceil(log2(N))，默认 W43/W44/W44/W45。anchor 同时增加相同进位位数，维持 `R×2^(anchor−(sumWidth−2))`。不能只加数据位宽、不修改 anchor。

将 sign 与 magnitude 分开对齐，避免从 PE 规格化结果先转补码、再取绝对值。零项不参与 MAX；所有零时内部基准 anchor 置 0；NaN/+Inf/−Inf 按加法规则归并。rounding/last 延迟到 S14，与数值同步继续流水。

有效位同步复位，无停顿。C 是每事务的显式输入，没有 accumulator 状态；连续对同一 D 进行递归累加时，调用方必须自行调度 18 拍依赖，不能以 II=1 推断反馈依赖每拍可解。

待 SV 验收：N=2/3/4/5、C 格式及 subnormal、dot 与 C 大数抵消、失活 PE 特殊值不污染结果、舍入模式逐拍切换、气泡和复位。只对齐和舍入有限精度 dot，既不改变 PE 合同，也不声称全链路无限精度。
