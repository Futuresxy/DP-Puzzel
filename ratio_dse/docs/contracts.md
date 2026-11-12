# 三个模型的共用数据与边界合同

JSON 为机器读取主格式，CSV 为长表导出。A/B 使用 `schema_version: 1`。实际字段、输入样例和复算入口见 [面积模型](../area_model/README.md) 与 [GEMM 模型](../compute_model/README.md)。C 行为后续调度和联合评价合同。

## 通用约定

- 所有输出含 `schema_version`、稳定 ID、状态、单位、模型/输入/源码 hash、命令和来源；嵌套元信息可统一放在 run manifest。
- 面积内部使用 µm²，汇总同时输出 mm²；频率 Hz，带宽 byte/s，周期整数，时间 s，功率 W，能量 J；1 MAC=2 FLOP。
- 未知值为 null 并给出 reason，unsupported 与 missing_evidence 分开。模型结果为 `analytical_uncalibrated`，校准须另给验证误差与适用范围。
- `ratio_label` 仅用于展示，能力由逐模式 `native_k` 和 II 推导。共享互斥模式不得相加成并发吞吐。
- `hardware_feasibility`、`quality_feasibility`、`metric_completeness` 分开记录；不能用一个 PASS 隐藏质量或功耗未知。

## 对象与责任

| 对象 | 生产方 | 最小字段 |
|---|---|---|
| HardwareProfile | A | profile_id, ratio_label, top, export_id, verification_id, dc_run_id, area_um2, frequency_hz, pvt, timing/electrical status, included_components, evidence_paths/hashes, artifact_availability |
| ModeProfile | A | profile_id, format_id, operand/scale/accumulator semantics, native_k, latency_cycles, ii_cycles, input layout, power_dynamic_w, power_leakage_w, power_total_w, power_run_id, activity_source, measured/proxy/missing status |
| ArrayScenario | A | scenario_id, constraint_kind, baseline_profile, baseline_cores, baseline_tensor_fraction, arrays_per_core, legal_shapes, broadcast_model, input_budget_bytes_s, supported_format_set, peripheral_policy |
| Deployment | A | deployment_id, profile_id, m_array, n_array, arrays_per_core, core_count, area_tensor/peripheral/core/pool, budget/unused_area, per_mode_peak_macs_s, input_demand_by_mode, excluded_components, validity |
| GemmWorkload | B | workload_id, metadata, operators: op_id, stage, segment, layer_id, category, subcategory, shape, dependencies, precision_label, useful_macs |
| OperatorEvaluation | B | workload_id, op_id, deployment_id, precision_plan_id, native_k, issue/RAW/drain cycles, useful/issued_macs, utilization, bytes_by_interface, conversion status/cost, calibration_status |
| PrecisionPlan / QualityRecord | B/C | plan_id, selected_ops, mappings: storage/multiply/scale/accumulator formats, execution_path, dp_mode, conversion; records: metric, reference/candidate value, delta, max_degradation, dataset/protocol, model_revision, quantizer_revision, provenance, status |
| CandidateEvaluation | C | candidate_id, view, deployment_id, workload_id, precision_plan_id, area_mm2, core_count, peak_macs_s_by_mode, latency metrics, power/energy metrics, quality/hardware status, exclusions, baseline_id, speedup, Pareto membership and objective set |

浮点族名不足以确定编码。具体格式未核验时，保留原标签并使 mode 未解析；显式代理可以运行敏感性分支，但必须带 `proxy_for`，不能冒充对应格式实测。

## 面积与部署

参考参数为 N0=36、alpha=0.30。基线 TensorCore 面积 AT0 包含该核心全部声明内阵列；外围 AO=AT0*(1/alpha-1)，总预算 Abud=N0*AT0/alpha。候选核心 ACj=AO+ATj，完整核心数 floor(Abud/ACj)，剩余面积显式报告。

ATj 首轮可采用 DP 实测面积×实例数，并明确未包括的阵列互连/控制增量；有依据的额外阵列成本单列。整个结果是面积估计，不是整核综合测量。不得同时计入完整核心 profile 和它已包含的阵列。

阵列 shape 由实验配置显式提供，不从旧论文 16×16、当前 spec 16×4 或历史 2×2 group 静默选择。不同来源允许作为有名字的分析场景，不能成为新 RTL 合同。

等阵列：固定 m_array/n_array/arrays_per_core。等输入带宽：固定每核本地存储→TensorCore 的物理预算，在声明的合法 shape 集合中枚举；同一候选所有模式使用同一 shape。首轮用允许模式的最大需求作饱和供数可行门禁，亦可输出明确标识的供数受限场景；不得偷偷降低预算检查的模式集合。

需求由 A/B 向量长度、存储打包、scale、广播范围、时间复用及频率计算。输出 C/D、其他存储层流量另计；等输入带宽不意味着输出、全芯片或 HBM 带宽相同。基线预算可由选定基线 shape 和模式集合推导，不能各候选自行改预算。

## GEMM 与执行精度

九配比最终集合：1:2:4、1:2:6、1:2:8、1:4:4、1:4:8、1:2:12、1:2:16、1:6:12、1:8:16。

第一阶段内置 V4/V4.1 的 Attention/MoE GEMM，四类为 attention_core、attention_projection、shared_or_dense_ffn、routed_expert。Indexer 属 Attention，但通过 subcategory 单列；残余/排除 GEMM 保持独立账本。FP32 等未支持计算报告其 FLOP 和排除原因。

| V4.1 算子 | 用户给定的目标执行标签 | 处理要求 |
|---|---|---|
| Main SWA/CSA QK、PV | BF16 | 分开 QK/PV 和局部/全局稀疏形状 |
| Grouped O-down | BF16 | 保存分组次数，不先合并为一个大矩阵 |
| Global-KV projection | BF16 | 目标映射与参考脚本分支分开，见下文 |
| Q-down/up/O-up、SWA-KV projection | FP8 | 解析具体 FP8 与 scale；未证实时不可默认为 MXFP8 |
| Shared Expert gate/up/down | FP8 | 每专家 token 分布与形状分开 |
| Index Q projection | FP8 | 单列 Indexer 子类 |
| Routed Expert gate/up/down | activation FP8 × weight FP4（W4A8） | 存储/乘法/转换分离，不能当原生 FP4 峰值 |
| Full Indexer QK | FP4 | 解析具体编码；与参考 fake-quantized 实现区别 |

本地 `paper/scripts/deepseek_v41.py` 的 `global_kv.projection` 在 ratio=2 分支为 FP32、其他分支为 BF16；Indexer 也区分 native 与 reference。B 应建立 `target_native_20261112` 和 `reference` 独立映射并输出差异，不能覆盖历史账本或宣称二者相同。V4 使用自身配置与映射。

现用 DP 原始 A/B 合同为同格式。W4A8 必须解析为有来源的执行路径，例如权重转换后采用两侧 FP8，并保留转换、scale 和功耗代理状态；转换路径未定时可以统计 useful work，但实际 mode 与时延置 unresolved。不得新增假定原生 FP8×FP4 指令。

## 利用率与时延

区分硬件参数 `(m_array,n_array,k_native[mode])` 与负载 `(M,N,K)`。简单 dense、整块填充、无跨任务打包时的容量占用示例：

```text
useful_macs = M*N*K*repetitions
issued_macs = ceil(M/m_array)*m_array
              *ceil(N/n_array)*n_array
              *ceil(K/k_native)*k_native*repetitions
shape_utilization = useful_macs/issued_macs
```

这是特定 tiling 的几何利用率，不是实际执行周期。稀疏、跨任务打包和 grouped/expert 执行必须使用各自实际 tile 账本。

分别输出 `shape_utilization`、`k_tail_utilization`、`temporal_utilization` 与 useful MAC/(声明资源峰值 MAC/cycle×测量窗口周期) 的 `effective_utilization`，写明分母；这些指标不要求盲目相乘。稀疏 MAC、填充 MAC 与冗余计算分开。

周期显式记录 issue、pipeline/fill/drain、RAW 等待、输入停顿、转换和调度；不可由 useful FLOP/峰值再叠乘同一种利用率两次。L8/II=1 只约束独立请求；同一输出跨 K 段的 C/D 依赖必须指定 feedback latency、驻留位置、上下文数或解析假设。

`gemm_compute_latency_s` 沿用项目数据契约，表示声明边界内 GEMM 完成时间，明确包括/排除项。另报 `ideal_compute_lower_bound_s`、`array_service_time_s`。缺少必要供数/转换条件时 completion 可为 null，下界单列，不能冒充实际完成时间。部分和外部读写与内部驻留分开。

## 多核、功耗与质量

C 采用明确的输出 tile 到核心分配。B 的 `tile_services.json` 按同 K 发射次数聚合输出 tile，单阵列周期为自身边界指标。C 首轮可使用顺序算子、独立 M/N tile 的确定性调度，K 段留在同核心。未使用核心计入容量和必要 idle/leakage。共享输入带宽若启用须显式分配。

DP 测量的活动来源不是 DeepSeek 实测；引用时标注 activity proxy。总功耗不能简单乘 utilization：动态、漏电、空闲和门控行为分开。若仅有 active 模式成本，可输出具名的 full-activity sensitivity，不得填补未知 idle 成本为零。外围/存储/互连能耗未知时，chip_total_energy_j 为 null，dp_compute_energy_j 保持其边界。平均功耗与能耗必须覆盖同一时间窗；没有瞬态数据则峰值功耗为 null。

质量是完整 precision plan 的外部评价，含 PPL/准确率、数据集、模型版本和量化方式。默认不假定各算子损失可加。`unknown` 不等于 0；质量约束启用时未知方案不能进入 quality-feasible Pareto，仍可进入带标识的硬件收益探索。质量预测/量化训练是后续任务。

## 待决项与阻塞粒度

1. 阵列 shape、广播/累加驻留、反馈与上下文数：未定时使用命名的 analytical scenario；不阻塞账本和面积计算，不声称 RTL 周期吻合。
2. 等输入带宽的 baseline mode 集、复用次数、packing：必须显式配置；未配置则只完成等阵列分支。
3. W4A8 转换路径、FP8/FP4 具体格式与 Global-KV 来源差异：未解析只阻塞对应 mode 评价，不阻塞其他算子。
4. 质量、idle/外围功耗与校准数据：未知分量为 null，按指标独立处理，禁止用旧硬件或任意常数填空。

任务 A 负责硬件与部署 schema，B 负责 workload/operator/precision schema，C 负责联合评价与质量筛选 schema。改公共字段时同步本文、生产者与消费者，避免后续任务各自定义同名异义对象。
