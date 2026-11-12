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
