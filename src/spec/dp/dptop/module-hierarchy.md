> 功能：定义 DP 模块层级与 S6 接入合同；范围：T1H2Q4E8、T2H4Q8E16、H16Q32E64（T8）与后续专用源；版本：v1.9.1；修改时间：2026-11-10 00:40:07 +0800；对应代码：现有文件链接见下文；dp_top v1.8 CModel/RTL 已实现并通过本批功能验证；三个混合顶层与Q32E64已迁移v1.9，E64保留旧实现。

# 模块层级、所有权与 S6 扩展点

基础 `dp_top` 使用[v1.8](dp-top-v1.8.md)，三个混合顶层和 Q32E64 使用[v1.9](mixed-precision-expansion.md)。
E64/dp_top_e 保留原合同；静态参数隔离旧实现。六种入口见[top 架构索引](top-architectures.md)，
完整验证及 PPA 见[交付报告](../../../../hw/power/records/v19_design_report_20261110.md)。

## 层级与时刻

```text
DP top：同一事务只计算一次 dot(A,B)+C
├── 请求控制、valid/last；C raw32 传递，S5 C 解包
├── group：基础四组，混合 top 再增加二/四个 E 或四个 QE 组
│   ├── scale 解包 S1、系数/指数加法 S2、A_raw S3
│   ├── lane[0]：A/B 解包、乘积、局部对齐或窄 pair、规约
│   ├── lane[1]：相同事务的另一组元素
│   └── group 合并/abs/scale/LZD，S5 原幅值 + A_raw + compare_exp
├── S6：active MAX、delta、一次双向移位、符号恢复
├── S7：基础/扩展 carry-save 合并，双行选择，唯一 CPA
└── S8：最终 LZD/FP32 RNE，或 INT32 固定切片；valid/last 输出
```

三层是同一八级流水的功能归属，不是每层再串联八周期。输入在沿 n 接收，S1 在该沿更新，
S8 在沿 n+7 更新；测试台在沿 n+8 更新前观察输出，因此 L=8、II=1。
只有顶层 A/B/C 原子接收；内部 fixed-latency valid，无独立 ready 或反压。
控制按拍推进，payload 由 valid/precision 使能保持，同步低有效 rst_n 取消在途事务。

## Lane 与 group 的职责

| 类型 | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| multi | 紧凑 A/B 解包 | 共享乘法、元素指数、T/H/Q 组 MAX | T/H/Q 对齐/符号化；E 窄 pair | 共享四项树，E 在末端融合局部 e2 | group 两 lane 和、abs、scale/LZD、token |
| E v1.9 | E 专用解包 | U4×U4→U8，S10 窄 pair | 四 pair 树并消费 HiF4 e2 | 窄组和/abs | U22 scale/旁路与 LZD，低补零为 U31，token |
| QE v1.9 | Q/E 专用解包 | U4 乘法，Q U5 指数 | Q 对齐；E 窄 pair 旁路宽移位 | 共享树，E 在末端消费局部 e2 | group 和/abs/scale/LZD、token |

多精度 T/H/Q 与 QE 的 Q 需要跨 lane MAX：lane 从 S1 字段生成指数候选和 active，group
组合选择并返回 MAX，S2 捕获；候选不依赖返回值，数据依赖无环。E 不依赖此 MAX，
HiF4 e2 在 lane 内消费，不传到跨 lane 对齐。E64 旧 E 路径的 S3/S4 划分以其冻结版本为准。

多精度/QE 默认 lane 和为 S31、group 和为 S32；专用 E v1.9 lane 和 S14、group 和 S15。
缩放前先分离符号和幅值，NVFP4/HiF4 使用 U14×U8，符号旁传。新版 E 的统一 U22
计数后低补零到 U31；非零值 LZD 与补零后的容器等价，零值另行屏蔽。
细节与参数范围见[E lane](../lane/dp_lane_E.md)、[QE lane](../lane/dp_lane_qe.md)、
[E group](../group/dp_group_E.md)、[QE group](../group/dp_group_qe.md)。

## S5 token 与 top 后端

group 输出 sign、原幅值、S10 A_raw、S10 compare_exp、zero/special。
`value = (-1)^sign × magnitude × 2^(A_raw-(M-1))`；非零组 `compare_exp = A_raw-clz(magnitude)`。
S5 不左移幅值。新版 C 不做 LZD，其 compare_exp=A_raw，非正规 C 保留 0.xxx。
旧 E64 保留 A_raw/z 合同，由静态分支兼容，不能把旧计数寄存与新版双指数混接。

S6 用有限非零 active 的 compare_exp 求 MAX，用 A_raw 计算移位量。
参与但为零的源与不支持本精度的源分别处理；special/负零归约不能只看非零 active。
额外组关闭时 MAX 和数值/特殊贡献均屏蔽；扩展寄存保持时，读端还要掩码旧数据。
默认对齐幅值 U39，恢复补码后为 S40；GLOBAL_W 参数改变时相关容器同步派生。

S7 的基础四组与唯一 C 先用 4:2/3:2 保留两行；新增二源直接用 4:2 合并，新增四源先
4:2 再与基础两行做 4:2。按模式选择两行后仅一个 CPA。E96 为 S43，E128/Q64E128 为 S44。
独立 Q32E64 没有基础/扩展选择，五源 4:2/3:2/CPA 为 S43；基础 dp_top 也为 S43。
INT8 只来自基础组，S6 固定 F7，INT32 输出取 [38:7]，不是总和最高32位。

## 源码阅读顺序

| 功能 | 维护中的主要模块 |
|---|---|
| 多精度解包 | dp_lane_unpack → dp_lane_operand_unpack → dp_unpack_atom |
| E/QE 解包 | dp_lane_unpack_e / dp_lane_unpack_qe |
| 元素乘法/指数 | dp_mantissa_bank、dp_exponent_bank / dp_qe_product_bank / E 的 dp_mul_unsigned |
| 局部对齐与规约 | dp_lane_align、dp_rtz_shift、dp_sum_tree、dp_lane_e_shift |
| group scale/计数 | dp_scale_unpack、dp_scale_multiply、dp_lzd，及各 group 内的组和/取幅值/anchor |
| 全局对齐 | top/common/dp_global_align、dp_mixed_global_align |
| 最终规约 | arithmetic/dp_final_csa_sum、dp_mixed_csa_sum；旧 E64 保留 dp_sum_tree |
| 输出 | dp_fp32_round、INT32 固定截取及 S8 DFF |

DFF 紧随本级组合计算、位于下一级消费之前，控制和数据同行。算术模块功能边界与寄存级
不要求一一对应。以具名 rN 与 ff_sN_sN 字段和 SIF 注释理解各级，不以 source 文件顺序推断周期。

## 复用与配置边界

共用算术库、分类型 lane/group、薄 top 静态装配已经用于六种架构；不是运行时选择完整架构。
`datatype` 是每请求精度，`frontend/profile` 是构建配置。固定的三个混合比及两个低精度比已实现；
任意源列表自动生成框架、仅 Q 组、Chisel 和阵列不属于本批实现。

新增 K 容量应在最终舍入前合并 S5 token，并且只加一次 C。新增独立 M/N 输出需要独立后端，
不能接入同一标量规约。资源复制与代码共用分别统计：多个实例引用同一定义仍各自占面积和活动成本。
源数增长时，MAX、移位器数、增长位及旁带延迟必须一起适配。当前全部 L8 已独立验证；
若未来增加流水、改变窗口或输入布局，须同步模型、spec、冻结回归与 PPA，不能继承现有验收。
