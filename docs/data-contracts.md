# 数据契约与可追溯性

本文定义文件的数据职责。DC 基础设施已实现 [RTL/验证输入 v2 契约](../hw/dc_syn/input-contract.md) 与 synthesis summary JSON/CSV，其余机器格式随实施确定；标识、单位和来源不能由隐式约定代替。已有 BF16 符号流水级示例的真实 RTL 验证及 DC 测量，尚无阵列/核心 characterization 或 workload power 数据。

## 通用记录

持久结果记录目的、时间、工艺、源码路径、输入 ID、工具版本、状态、单位和核心结果，详细参数/命令在对应 run。硬件链只保留一个 RTL 目录指纹，验证和综合引用同一值，不再为每份文件列指纹。输入修改形成新版本，已引用结果不能静默替换。

| 数据对象 | 生产方 → 消费方 | 核心字段与约束 |
| --- | --- | --- |
| FormatSpec | hw/spec → 实现、参考模型、DSE | format_id、来源版本、元素编码、block shape/scale 编码、累加/输出格式、舍入、特殊值、转换规则 |
| HardwareConfig | hw/configs → Chisel、characterization | hardware_id、scope、参数、支持模式、资源共享、接口、目标时序；不含整芯片实例配比 |
| RTLExport | 导出流程 → RTL 仿真、EDA | export_id、来源映射、files.f、单个 RTL 目录指纹、README |
| RTLVerification | SV testbench → EDA 门禁 | export/目录指纹、testbench/参考/向量路径与版本、精度/周期判据、日志、状态 |
| SynthesisResult | DC → profile、power | 短 run 名、目的、时间、源码路径、工艺/PVT、面积/时序、门控与层级策略、网表路径 |
| WorkloadActivity | trace 回放 → 功耗、校准 | workload/format/mapping、输入 hash、reset/warmup/active/stall/idle 窗口、层次、timescale、VCD/SAIF hash |
| PowerResult | EDA power → profile | export/netlist/activity、库/PVT、频率、annotation coverage、internal/switching/leakage/total、窗口与方法 |
| HardwareProfile | hw/characterization → DSE | scope、included_components、支持模式、吞吐/周期、面积与活动成本、证据/工况、适用区间与误差 |
| WorkloadSpec | workloads → 映射/调度 | M/N/K、batch、依赖、频次、A/B/C 格式、允许模式/质量证据、布局、缩放元数据、初始/最终数据位置 |
| ChipConfig | configs → 芯片模型 | 核心/阵列数量与类型、层级共享、频率、HBM/L1/L0 容量与性能、固定/排除成本 |
| DesignScenario | configs → 搜索/比较 | 基线、增配/重设计场景、变量范围、固定条件、面积/功耗/时延约束、workload 权重和报告口径 |
| MappingSchedule | mapper/scheduler → latency/power | tile 分配、移动、资源占用、模式切换、同步、有效/停顿/空闲计数、执行时间线 |
| CandidateEvaluation | 成本模型 → 搜索/报告 | 候选、area 分解、power 平均/峰值、latency 分解、可选能耗、可行性、缺失项与置信状态 |
| ParetoReport | 搜索 → 研究结论 | 比较组、非支配候选、基线收益、敏感性、未建模项和证据链 |

## 单位与主要输出

- area：组件可用 µm²，芯片报告统一 mm²；记录 synthesis/post-layout/analytical 来源。
- power：芯片报告使用 W；区分 workload 窗口平均与峰值，峰值注明时间粒度。平均测量不能推导精确峰值。
- gemm_compute_latency：GEMM 完成延迟，报告固定时间单位与起止边界；同时给出纯阵列周期、数据移动、转换、调度/同步与重叠明细。该字段不是仅指乘加器执行时间。
- energy：可选，J；平均功耗与时间必须属于同一窗口和硬件边界。
- throughput：MAC/cycle 或 MAC/s；如转 OP/s，明确 1 MAC=2 OP。共享模式峰值不可无条件求和。
- bytes：包含元素、缩放、元数据、填充与布局/对齐成本；复用与压缩各有依据。
- 时钟、带宽与延迟标记所属 domain；不得把跨域 cycle 混加。

## 数据状态

| 状态 | 含义 | 正式使用条件 |
| --- | --- | --- |
| planned | 只有规格或未填字段 | 不作为结果 |
| analytical_uncalibrated | 基于明确假设的解析估计 | 允许探索，不能冒充已校准 |
| rtl_verified | 指定 RTL 通过精度与周期测试 | 只证明功能，不证明 PPA |
| measured | 工具/真实负载测量证据完整 | 按测量范围使用 |
| calibrated | 模型经测量校准且有独立验证误差 | 在声明范围内使用 |
| invalid / stale | 输入不匹配、验证失败或证据失效 | 排除 |

导出具有 generated/verified/failed 生命周期，分析 run 和 profile 独立标记状态。缺失字段使用 unknown/null 语义，不以零或成功状态代替。

## 必须保持的关联

1. PPA 使用的 RTL 必须与通过 testbench 的 RTL 目录指纹一致；参考语义变化后重新核验验证证据。
2. 功耗窗口的 trace、映射、netlist、频率与数值模式保持一致；活动缺失不能当成零切换。
3. DSE 候选的硬件 profile、存储模型和 workload 可追溯到配置与预算，不跨工艺/电压/精度盲用测量。

完整 RTL、波形、EDA 报告、trace 和大型扫描输出留在受控归档；Git 保存核心定义、精简证据、归档 URI/hash 和复现步骤。
