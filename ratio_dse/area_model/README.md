# DP 面积、部署与绝对峰值

给定单 DP 的面积和逐格式能力，计算固定核心池预算下的整数核心部署、逐精度峰值与本地 A/B 饱和供数需求。支持固定阵列形状、固定每核 A/B 带宽两种场景。模型输出可直接供 [GEMM 模型](../compute_model/README.md) 和下游调度器读取。

## Quick start

在仓库根运行，使用 Python 3.11+ 标准库。

```bash
python3.11 -m ratio_dse.area_model \
  --evidence ratio_dse/configs/area/dp_n12_20261112.lock.json \
  --scenario ratio_dse/configs/area/equal_array.json \
  --output ratio_dse/results/my-run/area
```

换用 [equal_input_bandwidth.json](../configs/area/equal_input_bandwidth.json) 可枚举等输入带宽场景，输出目录须为新目录。社区数据使用 `--profiles hardware_profiles.json` 替换 `--evidence`。任一示例的 `hardware_profiles.json` 都可作为完整自定义输入模板。

## SM / AICore 拓扑与基线

在传给 `--scenario` 的 JSON 中设置 `core_kind` 为 `sm` 或 `aicore`。它标记面积预算和部署的计数单位。设置每个 SM/AICore 的 Subcore 数、每个 Subcore 的 TensorCore 数，以及**单个 TensorCore** 的 `baseline_shape`。

| 场景文件 | Subcore / SM | TensorCore / Subcore | 单 TensorCore 形状 | DP / SM |
|---|---:|---:|---:|---:|
| [sm_1x16x16.json](../configs/area/sm_1x16x16.json) | 1 | 1 | 16×16 | 256 |
| [sm_4x16x4.json](../configs/area/sm_4x16x4.json) | 4 | 1 | 16×4 | 256 |
| [sm_4x32x2.json](../configs/area/sm_4x32x2.json) | 4 | 1 | 32×2 | 256 |

每份场景里的 `baseline_cores: 36` 是基线 **SM/AICore 的个数**，`baseline_tensor_fraction: 0.30` 是一个基线 SM/AICore 内**所有 TensorCore 面积之和**占该 SM/AICore 面积的比例。两项可直接修改。面积模型计算

```text
DP/SM = subcores_per_core × tensorcores_per_subcore × m_array × n_array
基线核心池预算 = baseline_cores × 基线每 SM/AICore 的 TensorCore 总面积 / baseline_tensor_fraction
```

这三份是 256 DP 的解析实验配置。采用同一 DP、时钟、面积比例及零阵列增量时，基线面积和逐格式理想峰值相同。每个 TensorCore 按自己的形状计算广播和供数，各 TensorCore 的需求在 SM/AICore 层求和。计算模型也按单个 TensorCore 的 M/N 形状做 tiling。等带宽横向比较时可显式指定同一个 `input_budget_bytes_s`，避免各布局各自派生预算。

## 建模架构与带宽边界

```text
单 DP 的面积、native K、L、II、格式布局和功耗记录
  → TensorCore 的 M/N 形状、广播组和每拍发射量
  → SM/AICore 的 TensorCore 数、固定外围面积和本地供数需求
  → 同面积预算下的整数 SM 数、分精度峰值和供数余量
  → GEMM 模型 / DSE 按工作负载估算时间
```

面积模型在给定频率下用 `每 SM DP 数 × native_k / II × 频率` 算各精度峰值。DP 的 `L` 记录在 profile 中供时序模型使用。面积阶段的供数判断是**持续按 II 发射时，A/B 的平均供数是否够用**，计算和搬移的时间由下游根据具体 GEMM 求得。

当前带宽的计量切面是**每 SM 的本地操作数源向 TensorCore 输入侧交付预格式化 A/B 的有效带宽**。这个抽象端口可用具体硬件上对应的数据路径来标定。shared memory、collector/驻留缓冲和阵列内部端口在当前模型里合用一个有效供数切面，各自的带宽、容量、bank conflict 和链路时延尚无独立参数。跨 SM 互连和 HBM 属于上游路径。[TensorCore 存储与调度合同](../../src/spec/tensorcore/README.md#3-后续必须完成的合同)

每个格式先按 native K、打包、scale 和元数据求一个向量的字节数，再乘同次发射需要的独立 A/B 向量数。A 在同一行广播，B 在同一列广播，跨组共享由 `broadcast_model` 的两个开关决定。面积模型还接受 A、B 各自的**平均时间复用次数**。

```text
每 SM A/B 满速需求 = TensorCore/SM × 频率 / II
                  × (A 向量数 × A 向量字节 / A 复用次数
                   + B 向量数 × B 向量字节 / B 复用次数)
```

例如，四个 `16×4` TensorCore、`4×4` 广播组、1 GHz、基线 MXFP4 K=64 时，一个 A 或 B 向量为 32 B 数据加 2 B scale。无跨组共享时，每阵列每次发射读 16 份 A 和 16 份 B，满速需求是 **4.352 TB/s/SM**。若 A 在同一带宽切面平均装入一次、消费两次，B 仍逐次装入，则平均需求变成 **3.264 TB/s/SM**。这项参数只折算带宽需求。实现这种复用需要相同 A 的 tile 连续或重叠驻留，并满足缓冲容量与访问端口条件。C/D 流量单列。面积表里的 `dp_d_stream_bytes_s_per_core` 是持续发射时 DP 的 D 端口流量，GEMM 的最终写回按完成的输出 tile 另计。

| 场景 | 如何用带宽 |
|---|---|
| `equal_array` | 固定单 TensorCore 形状及每 SM 的数量。输出逐模式满速需求、预算余量和 `saturation_feasible`，保留供数低于峰值需求的候选。当前精度迁移图用此场景，再由 DSE 按选定带宽计算运行时间。 |
| `equal_input_bandwidth` | 用固定的每 SM 输入预算，要求 `supported_format_set` 内各模式都通过满速门槛。可在一个 shape 上筛选 DP 配比，也可枚举多个 `legal_shapes`。这个门槛适用于目标是持续满速发射的场景。 |

例如，固定 `4×16×4`、各模式默认复用次数为 1、预算 **8 TB/s/SM** 时，BF16、MXFP8、MXFP4 都满速的候选是 `1:2:4` 和 `1:2:6`。如果系统允许等操作数 ready，用 `equal_array` 保留其余配比，再比较带等待的 GEMM 时间。阵列驻留、ping-pong 及其硬件面积需要单独给定，本模型通过 `array_extra_area_um2` 接收已知增量。[供数公式与门槛实现](model.py#L130) · [下游数据搬移与计算](../compute_model/README.md#建模架构与周期)

## Inputs

| 参数或字段 | 说明 |
|---|---|
| `--evidence` | 仓库根相对路径和 SHA-256 固定的 DC、功耗、规格记录，另列各候选的顶层、比例与 L/II。按 DC 中的原生容量和功耗点的 logical K 交叉检查。记录缺候选时保留其 ID 与状态。 |
| `--profiles` | `schema_version: 1`，`profiles` 为数组。每项声明唯一 `profile_id`、`ratio_label`、`area_um2`、`frequency_hz`、`technology_id`、`pvt`、`clock_gating`、`status`、`included_components: ["dp"]` 和 `modes`。硬件来源使用 `top`、`export_id`、`verification_id`、`dc_run_id` 和 `evidence`。自定义假设应写入来源字段。 |
| `profiles[].modes` | 格式 ID 到模式的映射。每模式包含 `format_id`、正整数 `native_k`、`latency_cycles`、`ii_cycles`、`accumulator_format` 和 `input_layout`。布局使用 `element_slot_bits`、可空的 `scale_block_elements` / `scale_format`、`scale_bits`、可选的 `auxiliary_bit_periods`。功耗以 W 为单位，逐项给出 `power_dynamic_w`、`power_leakage_w`、`power_total_w`、`power_status`，未知值用 `null`。 |
| 基线与预算 | 场景 JSON 的 `schema_version` 为 1。提供 `scenario_id`、`baseline_profile`、`baseline_cores`、`baseline_tensor_fraction`（0 < α ≤ 1）、`peripheral_policy: "fixed_baseline"`。预算为每基线核的 TensorCore 总面积乘基线核数再除以 α。 |
| 形状与时钟 | `frequency_hz`、`subcores_per_core`、`tensorcores_per_subcore`、`baseline_shape: [m,n]`、含基线的 `legal_shapes`。同一场景内各 Subcore 使用相同结构。旧配置可继续单独提供 `arrays_per_core`，模型按一个 Subcore 计。等阵列使用 `constraint_kind: "equal_array"` 和单一形状。等带宽使用 `"equal_input_bandwidth"`。可选 `array_extra_area_um2` 为每 TensorCore 单列的增量成本，`shape_basis` 记录形状来源。 |
| 广播与带宽 | `broadcast_model` 声明 `group_shape`、`share_a_across_column_groups`、`share_b_across_row_groups` 以及正整数 `a_temporal_reuse` / `b_temporal_reuse`。组内 A 按行、B 按列共享。指定非空 `supported_format_set`，`input_budget_bytes_s` 可为数值、`"derive_from_baseline"` 或 `null`，等带宽场景需前两种之一。 |

输入带宽为每核心本地存储边界的平均饱和需求。供数按各侧独立、字节对齐的操作数向量计数，包含块 scale 及相应元数据。广播组允许最后一组不满，物理合法形状由实验者明确提供。等带宽场景使用指定模式中的最大需求作为基线派生预算，各候选的同一物理形状逐模式检查。等阵列场景显示供数余量，允许读取供数受限候选的几何峰值。

## Outputs

| 文件 | 行粒度与含义 |
|---|---|
| `hardware_profiles.json` / `profile_modes.csv` | 单 DP 和 DP×格式。面积、能力、活动窗口、功耗及来源状态。 |
| `deployments.json` / `deployments.csv` | 场景×DP×形状。含 `core_kind`、Subcore/TensorCore 个数、每 TensorCore/Subcore/SM 的 DP 数、整数核心数、每核和核心池面积、剩余面积、`valid` 和原因。JSON 含完整场景和基线部署 ID。 |
| `deployment_modes.csv` | 部署×格式。单核/核心池 MAC/s、核心池 TFLOP/s、A/B 需求、余量、每次发射工作集、D 流量及饱和可行性。 |
| `missing_evidence.json` | 缺少或不兼容的硬件/功耗记录。 |
| `manifest.json` / `summary.md` | 复现命令、配置、输入/源码/输出 SHA-256、模型版本与摘要。 |

单 DP 每模式峰值为 `native_k / ii_cycles` MAC/cycle，芯片每模式峰值再乘时钟和部署 DP 数。以 1 GHz、16×4、每核一阵列为例，`H16Q32E64` 部署 36 核，BF16/MXFP8 E4M3/MXFP4 E2M1 峰值为 **73.728 / 147.456 / 294.912 TFLOP/s**。同预算下 `H16Q128E256` 部署 22 核，对应 **45.056 / 360.448 / 720.896 TFLOP/s**。每个峰值使用共享硬件的单一模式。供数可行性由独立字段给出。

面积是单 DP 综合面积乘物理实例数，加声明的外围和阵列增量。当前默认覆盖核心池，HBM、封装和未表征的阵列增量位于边界外。DP 功耗来自 Qwen3-8B MLP 活动窗口，作为逐模式 DP 证据输出。整阵列时序、运行时吞吐和整芯片功耗需另外表征。

## Python API

```python
from ratio_dse.area_model import import_profiles, enumerate_deployments
from ratio_dse.common import read_json

profiles, evidence_paths = import_profiles(read_json("ratio_dse/configs/area/dp_n12_20261112.lock.json"))
result = enumerate_deployments(profiles, read_json("ratio_dse/configs/area/equal_array.json"))
print(result["baseline_deployment_id"])
```
