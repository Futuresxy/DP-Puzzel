# T2H4Q8E16 分组共享方案：八周期候选

状态：当前主方案的逻辑分段已提出；逐周期组合时序、精度位宽和 1.41 GHz 尚待推导/验证。本文件只描述近乎复用的分组共享设计；独立移位对齐保留在 [后续探索](independent-align.md)，不作为本轮实现默认路径。浮点目标 L=8；INT8 预计可缩短 2–3 个周期，准确 L 待定。

## 参数与数据依赖

基本组 FP16 K4 对应 T2H4Q8E16；每组两个 T1H2Q4E8 lane。FP16 K8/K16 由 2/4 个基本组并行，其跨组平衡和自然位宽分别增长 1/2 位。lane token 和组 token 的布局见 [容量合同](layout-and-scales.md)。

流水包含 A/B 解包与 TF32 复用解码、指数和/尾数乘法、lane 移位对齐与规约、基本组 scale 融合、跨基本组对齐归约、FP32 C 最终合并、LZD 与 RM norm。FP32 C 和 D 在 DP 内，不把 scale 融合、C 合并或输出打包移出 8 周期预算。

## 八级数据路径

| 级 | 主数据操作 | 模式差异与控制 |
| --- | --- | --- |
| S1 | 解包 A/B，拆 scale 与 HiF4 e1/e2 metadata，登记 C/mode/last | TF32 取 19 位有效字段，FP16 尾数与 BF16 指数通路复用；产生本级 valid |
| S2 | 解码指数/scale；形成乘积指数和、操作数分类 | TF32/FP16/BF16 共享指数解码结构的候选；scale 块 index 按 16 E 项映射 |
| S3 | 尾数定点乘法；构造带符号 product coefficient 与指数坐标 | INT8 走整数乘法；不适用浮点 scale/指数的分支隔离 |
| S4 | 每个 T1H2Q4E8 lane 独立参考指数比较并移位对齐 | FP16/BF16 lane 最多对齐 2 项，Q 4 项，E 8 项；TF32/INT8 单项路径可直通 |
| S5 | lane 内定点规约，并把同一基本组两个 lane 对齐合成 T2H4Q8E16 组结果 | 乘积和与 scale/e1 以有定义的公共定点坐标融合；不得提前丢失所需保留位 |
| S6 | 1/2/4 个基本组按最大 exponent 坐标移位并做平衡组间规约 | K4 直通，K8 1 层，K16 2 层；`group_sum_growth_bits=ceil(log2(group_count))` |
| S7 | 缩放点积组结果与 FP32 C 对齐并加和 | C 不乘 A/B scale；保留输出舍入所需的符号、指数和保护位 |
| S8 | LZD、RM 舍入、FP32 norm/打包并注册输出 | 输出 FP32 D、valid 和对应 last；INT8 模式按独立整数旁路规则输出 |

本表是数据依赖的分级目标，不保证任一候选在工艺 PVT 下单级达标。特别是 S4 lane MAX/变移位/求和、S5 scale 融合、S6 K16 两层平衡树、S7 C 对齐加法、S8 LZD+RM rounding 必须以具体总位宽综合与时序分析；如果单级过长，只能在 8 级内重排运算或更改共享边界，再更新此合同。

## INT8 快路径

INT8 并行度等于 Q，绕开浮点 exponent/scale/浮点 LZD/norm。依据用户目标，可以少走约 2–3 个 DP 周期；当前标为 **L=5–6 候选**，需待整数结果格式、C 语义、carry growth 与共享输出时序确定后再定 exact latency。INT8 输入输出是否通过同一 FP32 port 尚未闭合。模式在会话内固定，因此短路径不会和浮点结果交错；输出路径不引入 `ready` 背压。

## 必须闭合的时序依赖

1. S1→S3 TF32 高 19 位是否为 sign/exponent/mantissa 的确切映射及 H/BF decode 适配。
2. S4 lane 里的统一移位位置和负指数差/过大差的数值行为。
3. S5 的 product sum 如何融合 MX scale、HiF4 e1 与 e2；scale 数值可否仅换 exponent 仍待格式定义。
4. S6 K16 的两层和 S7 C merge 的位宽，使 S8 LZD+RM norm 可在一个周期完成。
5. 定点小数点、25/35/约37位保留窗口以及两种共享乘法器/移位器的具体边界。

上述问题闭合并经 CModel 精确描述后，再把候选流水实现为 Chisel 与手写 Verilog。分级表不等于 1.41 GHz 已通过。
