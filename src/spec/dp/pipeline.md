> 功能：定义分组共享 DP 的流水候选；范围：S1–S8、INT32 共用输出和时序待决项；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（对应模块文件未建，文件映射待定义）。

~~# T2H4Q8E16 分组共享方案：八周期流水 v1.2~~

# T2H4Q8E16 分组共享方案：八周期流水 v1.3

~~旧标题：八周期流水 v1.2。~~

~~T2H4Q8E16 分组共享方案：八周期流水 v1.1（旧标题）~~

状态：用户确定本图的数据依赖和阶段组织，浮点与 INT8 当前统一 L=8、目标 II=1；S2/S3 标量边界、S5/S6/S8 组合时序仍待验证。~~INT8 在 S8 直接输出 INT32，未启用早出旁路。~~

~~**v1.1 当前定义：** INT8 在 S8 直接输出 INT32，未启用早出旁路。模块归属与未来 S6 专用源接入见 [模块层级](module-hierarchy.md)；当前基线八级，未来扩展 profile 的额外 1–2 级不用于放宽本基线。旧八级分配见下方删除线记录。~~

~~**v1.3 当前定义：** 首选全格式 L8，INT8 无早出；S5 增加 scale 后规格化。用户现允许若该级不能满足时序，单独拆出规格化一级形成 L9 备用 profile；不因此自动启用，也不涉及先前 Q/E/QE 扩展的其他级数。~~

**v1.3 当前定义：** 首选全格式L8；S5 scale后LZD只计数，S6一次双向移位。必要时允许L9备用拆检测/指数准备；INT无早出。

## 当前八级划分

| 级 | 数据路径 | 指数、scale 与控制并行路径 |
| --- | --- | --- |
| ~~S1~~ | ~~A/B/C/scale 解包；A/B 固定 E/M/S；HiF4 e1 融入幅值；INT8 变符号+八位幅值~~ | ~~C 浮点分类及有效指数、INT32 C 的整数解释；scale 统一 E8M3；采样 mode/valid/last~~ |
| S1 | A/B/scale 解包；HiF4 e1 融合、INT8 sign/abs；保存原始 C32 | 逐笔采样 A/B/C/scale datatype，派生 ctrl；C 不解包，raw32 与 c_datatype 传至 S4 |
| S2 | 每 lane 两组四单元尾数乘法，含 T/FP16 和 INT8 部分积重构 | 8+8→9、5+5→6 指数加法；lane MAX→两个 lane 的基本组 MAX；scale 指数和及 4×4 系数积 |
| ~~S3~~ | ~~T/H/Q 使用四个共享幅值移位器，向零截断后符号化；E 八项先合四个 pair，补保护低零并作 HiF4 e2 差值移位；INT8 固定落位~~ | ~~消费基本组共同 MAX 与每项指数，计算 delta；共同 anchor、scale 修正和 C 逐级传递~~ |
| S3 | 四个固定 W-bit 共享移位器：T/H/Q 经输入 mux 复用，默认 W27；E pair/小范围精确移位与 INT8 结构落位走旁路 | 本级 ctrl 选择数据/sign/delta 和输入隔离；公共 r、scale、C raw32 与 valid/last 同行 |
| ~~S4~~ | ~~共用四路两层规约树：Q/E/INT8 四项，H 复用末层，T 单项直通同一输出边界~~ | ~~同步基本组共同 anchor、scale 系数/指数、分类、C、valid/last~~ |
| S4 | 共用四路两层规约树：Q/E/INT8 四项，H 复用末层，T 旁路同一边界 | 同步 r、scale、special、ctrl/valid/last；C 仍为 raw32 |
| ~~S5~~ | ~~两个 lane 相加；NVFP4/HiF4 紧凑组和乘 scale 系数，其他模式旁路；输出独立符号+幅值+anchor/F/zero/special~~ | ~~完成或透传元素/scale bias 与静态小数点修正；可预计算全局比较信息，但不能忽略 S5 实际组和为零的依赖~~ |
| ~~S5~~ | ~~两 lane 合并、NV/HiF4 scale 注入及 sign/magnitude；并行把 C raw32 按本笔 c_datatype 解包为 FP32 或 INT32~~ | ~~输出组 top-anchor、zero/special；C 分类/幅值/anchor 同拍注册；逐笔 ctrl 同行~~ |
| ~~S5~~ | ~~两 lane 合并 → scale 乘法/旁路 → 安全 sign/abs → 最终 SOP 的 LZD → 左移规格化~~ | ~~bias/静态坐标先准备，最终 e=A_raw-l；C 并行解包并规格化；组/C token 同拍注册~~ |
| S5 | 两 lane 合并 → scale 乘法/旁路 → 安全 sign/abs → LZD 只产生计数z；SOP不左移 | 注册原幅值/A_raw/z及zero/special；C并行解包、子正规检测z；控制同行 |
| ~~S6~~ | ~~所有基本组 token 与 C 按有效 top anchor 比较，求 delta，幅值移位向零截断，再转补码；INT8 仅作可逆低零落位~~ | ~~当前全局对齐总宽初值 W40（含符号）可扫参；C 指数和幅值在这里与所有 SOP 汇合~~ |
| ~~S6~~ | ~~规格化组与 C 取真实指数 MAX，求 unsigned delta，幅值右移 RTZ，再转补码~~ | ~~当前全局 signed W40 可扫参；INT8 仅结构落位，所有字段使用同行 ctrl~~ |
| S6 | 由A_raw-z求实际指数并MAX，按net=z-d=A_raw-E_max一次双向幅值移位，再转补码 | 正net左移、负net右移RTZ；默认signed W40；INT仅结构落位 |
| S7 | 一棵树直接求和 group_count 个组结果与 C，保留全部增长位 | 包含 C 的扇入数 2/3/5，深度 1/2/3；旁带持续推进 |
| ~~S8~~ | ~~浮点 abs/LZD/规范化/RNE/FP32 打包；INT8 删除结构低零后输出 INT32 低 32 位~~ | ~~特殊结果固定同延迟选择；INT32 回绕，溢出写入验证 trace；输出 out_valid/out_last~~ |
| S8 | 浮点 abs/LZD/norm/RNE/FP32；INT8 删除结构低零后 INT32 回绕 | out_valid/out_last/out_d_datatype 对应同一请求；不同格式均 L=8 |

~~下图为v1.2简图，未包含S5的z字段与S6双向控制；当前完整图见本页v1.3数据流。~~

```mermaid
flowchart LR
 S1["S1 A/B/scale 解包；采样逐笔 ctrl"] --> S2["S2 尾数乘 + 指数和/MAX"]
 S2 --> S3["S3 mux + 共享幅值移位 / E pair"]
 S3 --> S4["S4 共用四路树"]
 S4 --> S5["S5 两 lane / scale / 符号幅值"]
 C["C raw32：S1–S4 寄存"] --> C5["S5 FP32 / INT32 C 解包"]
 S5 --> S6["S6 组与 C 的 MAX/delta/幅值移位"]
 C5 --> S6
 S6 --> S7["S7 组数+1 路求和"]
 S7 --> S8["S8 FP32 / INT32 + datatype/last"]
```

~~C 在 S1 完成解包，S2–S5 只随对应事务透传；若将全局 MAX 提前到 S5，C 指数可提前用于该标量比较，C 幅值仍在 S6 首次参与对齐。所有特殊值、valid/last 与数据逐级匹配；输入 bubble 不停顿在途流水，mode 仍在 last 输出后切换。~~

**v1.2 当前定义：** C 仍在沿 n 与 A/B 原子接收；S1–S4 只传一份顶层 C raw32 及 c_datatype，S5 读取 S4 原值完成分类/解包，S6 首次对齐，S7 加 C。新增 C 解包不串接在组 scale 数据路径后。datatype/ctrl、特殊摘要、valid/last 随对应数据推进；相邻请求可换型，last 不引发排空。

## S2 的跨 lane MAX 与 S3 差值

S2 的 MAX 回传是同一周期中的有向组合路径，不是跨周期握手或组合反馈环。每个基本组把两个 lane 的有效乘积指数选出共同最大值，再送回各 lane；T/H/Q 在 S3 全部按这个共同坐标移位，因此 S5 合并不再需要第二次 lane 对齐。

候选优先在 S2 注册共同 MAX 和各项指数，S3 做 delta+移位+符号化。若时序允许可把 delta 提前到 S2；若不允许，不增加第九级，而在 S2/S3 内重排。S2 须检查指数加法→lane MAX→基本组 MAX 的延迟与布线，S3 须检查减法→W27 逻辑移位→符号化的延迟。

## 全局 MAX 能否放在 S5

~~组的 anchor 与 F 可以提前算，实际零组状态取决于 S5 求和/scale 结果。稳妥候选是在 S6 对 S5 已注册的组 token（包含 zero）及 C 做 MAX/delta/移位。如果要把 MAX 提前至 S5，必须把零屏蔽、特殊值屏蔽及 C 比较一并满足，并预算求和→zero 检测→MAX 路径。不得为省时序让完全抵消的高 anchor 零组压低其他小结果。~~

~~**v1.3：** 静态 A_raw 可以提前准备；实际 e=A_raw-l 必须等最终 scale 后幅值检测。S6 对已注册的规格化 token 做全局 MAX，不将其提前到 S5。零/特殊源独立屏蔽。~~

**当前：** 静态A_raw可提前准备；e=A_raw-z依赖scale后计数。S6对原幅值/A_raw/z的token生成e并MAX；如把e预计算到S5，需记录寄存字段且保持原坐标可重建。

## 时序与完整计算预算

1. S2 T/FP16 部分积重构及 INT8 两个交叉乘积重构；指数/MAX 与尾数乘法是并行路径。
2. S3 delta+27 位幅值移位+符号化；E pair 加法与最大两位精确移位。
~~3. S5 两 lane 相加→紧凑化→scale 系数乘法→符号/幅值输出。~~

~~3. **v1.3 S5：** 两 lane 相加→紧凑化→scale 系数乘法/旁路→安全 abs→LZD→左移；A_raw 预计算与数据链并行，但 e 修正等待 l。C 解包/子正规规格化是另一条并行路径。~~

3. **当前S5：** 两lane和→紧凑scale乘法/旁路→安全abs→LZD计数。C解包/子正规计数并行；S5无动态左移。S6需预算e生成→MAX→net→方向mux/移位。
4. S6 最多四组+C 的有效 anchor MAX、减法、幅值移位与符号恢复。
5. S7 最大五项宽位数规约，S8 abs/LZD/规范化/舍入进位链。

每项都在八周期内完成；当前没有 1.41 GHz 通过证据。可调整组合算子位置或采用压缩树/并行标量预处理，但必须保持共同参考指数、截断点和接口位精确语义，并更新受影响的观察点。

## 统一输出观察时刻

以沿前采样计账：请求沿 n 接收并更新 S1；S8 在 n+7 更新，结果由下游/TB 在 n+8 更新前观察，因此 L=8。CModel 与 RTL 必须采用同一个观察相位，见 [控制](control.md)。这不增加第九级或额外输出队列。

## 数值与资源交叉合同

- [乘法器共享](multiplier-sharing.md)：每 lane 两套 HH/HL/LH/LL、INT8 路由与 operand isolation。
- [数值布局](numeric-layout.md)：W27 幅值/W28 补码、E W15 紧凑组和、独立符号/幅值接口、全局窗口、树宽度和 RNE/INT32。
- [scale 与 bias](scale.md)：E8M0/E4M3/E6M2 到 E8M3，元素与 scale 的偏置只扣一次，C 比较前完成统一坐标。

## v1.1 流水图（已替代）

~~旧图将 C 放在 S1 解包；v1.2 改为上图的 S5 并行 C 支路。~~

```mermaid
flowchart LR
 S1["S1 解包 A/B/C/scale"] --> S2["S2 尾数乘 + 指数和/MAX"]
 S2 --> S3["S3 delta/幅值移位 + E pair"]
 S3 --> S4["S4 共用四路树"]
 S4 --> S5["S5 两 lane 合并/scale/符号幅值"]
 S5 --> S6["S6 组与 C 的 MAX/delta/幅值移位"]
 S6 --> S7["S7 组数+1 路求和"]
 S7 --> S8["S8 FP32 RNE / INT32 回绕"]
```

## v1.0 八级候选（已替代）

以下删除线只记录旧合同；其中“当前”字样仅代表当时草案，v1.1 的生效分工为上表。

~~T2H4Q8E16 分组共享方案：八周期候选~~

~~状态：当前主方案的逻辑分段已提出；逐周期组合时序、精度位宽和 1.41 GHz 尚待推导/验证。本文件只描述近乎复用的分组共享设计；独立移位对齐保留在 [后续探索](independent-align.md)，不作为本轮实现默认路径。浮点目标 L=8；INT8 根据整数乘积规约、加 C 和输出寄存边界重新切分，不预先承诺少几个周期。~~

~~参数与数据依赖~~

~~基本组 FP16 K4 对应 T2H4Q8E16；每组两个 T1H2Q4E8 lane。FP16 K8/K16 由 2/4 个基本组并行，其跨组平衡和自然位宽分别增长 1/2 位。lane token 和组 token 的布局见 [容量合同](layout-and-scales.md)。~~

~~流水包含 A/B 解包与 TF32 复用解码、指数和/尾数乘法、lane 移位对齐与规约、基本组 scale 融合、跨基本组对齐归约、FP32 C 最终合并、LZD 与 RM norm。FP32 C 和 D 在 DP 内，不把 scale 融合、C 合并或输出打包移出 8 周期预算。~~

~~八级数据路径~~

| ~~级~~ | ~~主数据操作~~ | ~~模式差异与控制~~ |
| --- | --- | --- |
| ~~S1~~ | ~~A/B 转为固定 E/M/S 布局；拆 scale/HiF4 metadata，分类 A/B/C 特殊值，登记 C/mode/last~~ | ~~见 [解包](unpack.md)；分类与有限数解码并行，不丢失 NaN/Inf/zero/subnormal 信息~~ |
| ~~S2~~ | ~~解码指数/scale；形成乘积指数和与乘积特殊值摘要~~ | ~~TF32/FP16/BF16 共用指数解码候选；scale 块 index 按 16 E 项映射~~ |
| ~~S3~~ | ~~尾数定点乘法；构造带符号 product coefficient 与指数坐标~~ | ~~INT8 走整数乘法；不适用浮点 scale/指数的分支隔离~~ |
| ~~S4~~ | ~~每个 T1H2Q4E8 lane 独立参考指数比较并移位对齐~~ | ~~FP16/BF16 lane 对齐 2 项，Q 4 项；E2M1 元素共用定点坐标，HiF4 lane 共用 e2，元素内无需浮点变移位；T 单项和 INT8 也不需该对齐~~ |
| ~~S5~~ | ~~lane 内定点规约，并把同一基本组两个 lane 对齐合成 T2H4Q8E16 组结果~~ | ~~乘积和与适用 scale 以有定义的公共定点坐标融合；E 元素指数/e1 按解包合同前移融合~~ |
| ~~S6~~ | ~~1/2/4 个基本组按最大 exponent 坐标移位并做平衡组间规约~~ | ~~K4 直通，K8 1 层，K16 2 层；`group_sum_growth_bits=ceil(log2(group_count))`~~ |
| ~~S7~~ | ~~缩放点积组结果与 FP32 C 对齐并加和~~ | ~~C 不乘 A/B scale；保留输出舍入所需的符号、指数和保护位~~ |
| ~~S8~~ | ~~LZD、RM 舍入、FP32 norm/打包并注册输出~~ | ~~输出 FP32 D、valid 和对应 last；INT8 模式按独立整数旁路规则输出~~ |

~~本表是数据依赖的分级目标，不保证任一候选在工艺 PVT 下单级达标。特别是 S4 lane MAX/变移位、S5 lane/基本组求和与 scale 融合、S6 K16 两层平衡树、S7 C 对齐加法、S8 LZD+RM rounding 必须以具体总位宽综合与时序分析；如果单级过长，只能在 8 级内重排运算或更改共享边界，再更新此合同。~~

~~特殊值摘要随 valid/last 同步经过全部级，在 S5/S6 汇总局部例外，在 S7 合并 C 分类，S8 按数值规则选取 NaN/Inf/有限结果。不增加额外异常流水周期，也不因特殊输入提前输出。NaN/Inf 编码不直接送入普通指数 MAX/尾数树。~~

~~INT8 快路径~~

~~INT8 并行度等于 Q。保留整数解包、乘法、lane/基本组/跨组累加和加 C；整数均在固定二进制坐标下求和，无浮点指数移位对齐，不能旁路求和树。纯整数输出无需 LZD、归一化和浮点舍入，缩短延迟应根据这些逻辑被省去后的寄存边界推导。~~

~~当前先定义功能顺序为 `整数解包 → 整数乘法 → 分层平衡规约 → 加 C → 整数输出`。功能步骤不等于五个周期：可以合级或因树深拆级，待位宽与时序分析后确定 `L_int8≤8`。若 C/D 仍按数值 FP32 解释，则整数与浮点的转换/对齐/舍入仍需实现，不能同时宣称全旁路；因此 INT8 C/D 的位解释是开始该路径 CModel 前的待决项。模式会话隔离保证短路径不和浮点结果交错。~~

~~必须闭合的时序依赖~~

~~1. S1→S3 按已确认的固定 E/M/S 解包，T/FP16 为 I1F10、Q 重编码 bias=15；需核验共享乘法器对应的 coefficient/指数坐标。~~
~~2. S4 lane 里的统一移位位置和负指数差/过大差的数值行为。~~
~~3. S1 E2M1 指数/HiF4 e1 融入定点 M 后，S2–S6 如何处理剩余 e2 和块 scale；scale 数值可否仅换 exponent 仍待格式定义。~~
~~4. S6 K16 的两层和 S7 C merge 的位宽，使 S8 LZD+RM norm 可在一个周期完成。~~
~~5. 定点小数点、25/35/约37位保留窗口以及两种共享乘法器/移位器的具体边界。~~

~~上述问题闭合并经 CModel 精确描述后，再把候选流水实现为 Chisel 与手写 Verilog。分级表不等于 1.41 GHz 已通过。~~

## 历史修订对照

以下为本次版本化时恢复的历史草案对照；删除线内容已被替代，不作为当前实现依据。较早内容尚无正式版本号，来源按真实提交或用户确认记录，不追认其为已批准合同。

- **INT8 延迟候选**：~~L=5–6 候选，预计缩短 2–3 周期。~~ → **当前：**不预设缩短周期数，按保留的乘法/规约/加 C 与省去的浮点逻辑切分。（来源：dba8ecf → 42350c5，旧候选摘要）

- **E 路径融合位置**：~~S5 融合 scale/e1。~~ → **当前：**元素指数/HiF4 e1 按已定解包前移至 S1；后续只处理剩余 e2 与块 scale，避免重复施加。（来源：dba8ecf → 42350c5，解包细化）

## v1.2：逐级数值与模块统计

每级 SM/TC、SxIxFx、r/alpha/top-anchor 的范围和位宽见 [出口表](stage-formats.md)。固定输入 mux 复用与参数窗口见 [移位器](shifter-sharing.md)；模块、寄存器与后端归属见 [面积/功耗统计](resource-accounting.md)。这些边界均属于同一八级，不因拆功能模块新增周期。S5 的 C 解包为独立并行支路，也需纳入时序检查。

## v1.2.1：组输出 LZD 的时序候选

~~[组规格化候选](group-normalization-options.md) 比较精确 LZD＋合并移位及粗粒度检测。S5 放 LZD 会延长组和/scale/abs 路径，S6 放 LZD 则延长 MAX/shift 前的路径；当前尚未选择或改变八级分工。C 的非正规输入也需考虑实际最高位。不能只提前静态 bias 就宣称解决了 SOP 抵消后的指数检测依赖。~~

~~**v1.3：** 已按用户选择把完整规格化放在 S5 的 scale 乘法之后；合并移位/粗粒度为未采用对照。S5 到 LZD 的实际数据依赖必须计入时序。~~

**当前：** S5 scale之后只做LZD计数；合并双向移位已选为S6主方案，完整双单向和粗粒度版仅作对照。

## v1.3：当前首选数据流与 L9 条件备用

```mermaid
flowchart LR
 S4["S4 lane SOP"] --> ADD["S5 两lane合并"]
 ADD --> MUL["scale乘法 / 旁路"]
 MUL --> ABS["安全sign/abs：m_raw"]
 ABS --> Z["LZD：只产生z"]
 ABS --> REG["S5寄存 m_raw / A_raw / z"]
 Z --> REG
 A["bias与静态坐标修正：A_raw"] --> REG
 REG --> E["S6 e=A_raw-z / MAX"]
 C["S5 C解包 / 仅计数z_c"] --> E
 E --> NET["net=z-d=A_raw-E_max"]
 REG --> SHIFT["S6一次双向移位"]
 C --> SHIFT
 NET --> SHIFT
 SHIFT --> S7["S7符号总和"]
 S7 --> S8["S8 norm/RNE 或 INT32"]
```

S5没有动态左移器；S6直接用A_raw-E_max可避免MAX后串联d再减z两次减法，数值等价，trace仍显示e/d/z/net。e=A_raw-z若提前在S5计算并寄存，是后续等价时序优化，需要预算LZD后标量减法及接口字段；当前基础接口明确原anchor+z。

首选全格式L8。若S5检测链或S6指数比较链过长，可设置构建期post_scale_norm_extra_stage=1（默认0）：S5组和/scale及C解包，新增S6完成abs/LZD计数与anchor准备，S7全局MAX/一次双向移位，S8总树，S9最终编码。该备用仍不实例化前置动态左移器。C/INT/special/ctrl/valid/last同拍顺延，latency=8+该参数，全格式同L，不引入乱序。

这是用户允许的必要时多一级，不是已选9级；CModel/RTL后续按同配置记录真实寄存边界，L8/L9算术须bit-exact。两段单向方案也保持同一数学参考，另列面积/功耗/关键路径对照；未运行EDA。沿n接收，末级在n+L-1更新，沿n+L更新前观察。

## 本轮未提交草案对照：v1.3：当前数据流与必要时的 L9 分拆

~~## v1.3：当前数据流与必要时的 L9 分拆~~

~~`flowchart LR`~~
~~`S4["S4 lane SOP"] --> ADD["S5 两 lane 合并"]`~~
~~`ADD --> MUL["scale 乘法 / 旁路"]`~~
~~`MUL --> ABS["安全 sign/abs"]`~~
~~`ABS --> LZ["最终幅值 LZD"]`~~
~~`LZ --> LEFT["左移规格化"]`~~
~~`A["无偏 A_raw 预计算"] --> E["e = A_raw - l"]`~~
~~`LZ --> E`~~
~~`LEFT --> REG["S5 组 token 寄存"]`~~
~~`E --> REG`~~
~~`C["S4 raw C"] --> CN["S5 解包 / 子正规规格化"]`~~
~~`REG --> S6["S6 signed MAX / unsigned delta / 右移 RTZ"]`~~
~~`CN --> S6`~~
~~`S6 --> S7["S7 完整求和"]`~~
~~`S7 --> S8["S8 norm / RNE 或 INT32"]`~~

~~上方旧 v1.2 简图未画出规格化，此图及本页当前表为 v1.3 的完整依赖。S5 左移精确，不产生 RTZ；S3/S6 的两个 RTZ 截断点仍保留，S6 网格坐标发生变化。~~

~~若 S5 未满足目标周期，可用构建期 `post_scale_norm_extra_stage=1`（默认0）：S5 完成组和/scale 并寄存未规格化 coefficient/坐标，S6 专门安全 abs/LZD/左移/修正 anchor，S7 全局对齐，S8 总树，S9 最终编码。C 仍在 S5 解包；L9 时其规格化可在新增 S6 完成，与组同步。INT、特殊摘要、ctrl/valid/last 同样通过新增一级，所有格式同为 L9，不引入结果乱序。~~

~~`latency=8+post_scale_norm_extra_stage`；L8 首选，L9 是用户授权的时序备用，尚未选择。沿 n 接收、末级在 n+L-1 更新、TB 在 n+L 更新前观察。每个 profile 必须在配置/trace/验收中显式记录；数值结果应完全一致，只移动寄存边界。未取得实现和工艺时序证据前，不宣称任一 profile 达到1.41 GHz。~~

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](../document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 重排 S2 并行乘/指数、S3 移位、S4 规约、S5 scale/sign-magnitude、S6+C 对齐、S7 总和、S8 FP32/INT32。 | 用户架构图与补充；[总时间线](../CHANGELOG.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | C 从 S1 解包改为 S1–S4 raw32、S5 解包；保持 L8；同步共享移位/控制/输出类型。 | 用户本轮要求及确认；[总时间线](../CHANGELOG.md) |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 讨论/说明补充 | 记录组实际指数候选及对应数值、特殊值或资源边界；不改变 v1.2 主路径。 | 用户 LZD/指数/特殊值讨论；[总时间线](../CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 按用户最终选择，S5 scale后LZD仅计数、S6一次双向移位；同步数值/接口/资源/备用周期，保留对照。 | 用户最终双向移位选择；[总时间线](../CHANGELOG.md) |
