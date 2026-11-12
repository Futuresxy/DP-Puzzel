# GEMM 工作量与精度迁移

将模型配置和运行场景转换成逐算子 GEMM 账本。可选地读取 [面积模型](../area_model/README.md) 的部署，对同一工作量的多个精度方案计算 native-K tiling、单阵列服务和声明接口边界内的完成时间。使用 Python 3.11+ 标准库。

## Quick start

从仓库根运行。第一个命令只生成工作量和精度账本。第二个命令在同一部署上比较两个方案，`my-run/area` 由面积模型的 Quick start 生成。输出目录须为新目录。

```bash
python3.11 -m ratio_dse.compute_model \
  --scenario ratio_dse/configs/compute/v4_prefill.json \
  --output ratio_dse/results/my-run/v4

python3.11 -m ratio_dse.compute_model \
  --scenario ratio_dse/configs/compute/v41_prefill.json \
  --plan ratio_dse/configs/compute/adapter_plan.json \
  --plan ratio_dse/configs/compute/grouped_o_down_fp8.json \
  --area-run ratio_dse/results/my-run/area \
  --array-model ratio_dse/configs/compute/serial_local_array.json \
  --output ratio_dse/results/my-run/v41
```

V4.1 示例选择简化 prefill、batch 1、256 tokens。在第 0–19 层把 Grouped O-down（`o_group`）迁至 MXFP8 E4M3，共迁移 **171,798,691,840 useful MAC**。示例保留在线激活转换成本为未知，仍可查看迁移前后的 native-K 形状和服务周期。

[合成 GEMM](../configs/compute/synthetic_gemm.json) 可通过 `--workload` 导入，再用 [合成 MXFP8 计划](../configs/compute/synthetic_gemm_fp8.json) 对照 BF16。固定 16×4 基线阵列，输入 (M=17,N=5,K=33) 时，useful MAC 均为 2,805。BF16 与 MXFP8 分别发射 12,288 和 16,384 MAC 容量，阵列服务为 27 和 19 周期。在示例声明的本地端口、缓冲与预转换假设下，单阵列完成时间为 42 和 30 ns。两类示例及面积枚举均可用 [run_examples.sh](../run_examples.sh) 执行。

## 接入新模型

从 [最小 GEMM JSON](../configs/compute/synthetic_gemm.json) 复制结构，用 `--workload` 导入。文件根部提供 `schema_version: 1`、`workload_id` 和 `operators`。工作负载已按特定 batch、token 数和阶段展开时，可在 `metadata` 中注明模型版本、运行场景和来源。

每个 GEMM 提供稳定的 `op_id`、阶段/层/算子标签、`shape`、`precision_label` 和 `dependencies`。常规线性层只需 M/N/K 与次数，MoE 提供逐专家 token 数，稀疏 Attention 为 QK/PV 分别给有效 key 长度或块位置。若执行精度有混合输入、块 scale 或转换，再用 `--plan` 指定实际格式和执行路径。只给账本即可统计用量，配上面积模型输出和数组配置才能评价周期。

若希望用户只交模型配置与 batch/token 场景，由开发者编写一个 adapter，将这些输入展开为同一份 GEMM 账本。静态配置可提供层数和张量维度，路由、稀疏选择和缓存日程由 adapter 的具名假设或运行观测提供。

## Inputs

| 文件或参数 | 粒度与要求 |
|---|---|
| `--scenario` | `schema_version: 1`，`model_id` 选 V4 Flash、V4 Pro 或 V4.1 Flash 的仓库注册名，可给 `model_revision` 和 `--model-config path/to/inference/config.json`。另给 `stage`、`schedule`、`variant`、`batch`、`past_tokens`、`query_tokens`、`routing_policy`。V4 prefill 选 `full`，V4.1 选 `simplified`、`ced` 或 `full`，三者接受冷启动输入。Decode 用 `stage: "decode"`、`schedule: "decode"`，每步单独记录，V4.1 decode 需要正数历史长度。 |
| `variant` | `reference` 复现参考 Indexer 执行路径与精度，`target_native_20261112` 使用目标分支。V4.1 ratio=2 的 Global-KV projection 在参考分支为 FP32，在目标为 BF16。两者使用同一场景比较，`reference_diff.csv` 显示 shape 和历史算量差异。 |
| `--trace` | 可选 `schema_version: 1`，`ops` 是 `op_id` 到观测的映射。专家记录提供按专家 ID 排列的 `tokens_per_expert`，守恒总 assignment。稀疏记录提供 `key_rows: [{"key_indices": [0, 3], "repetitions": 1}]`，key 从 0 开始、升序唯一。可选 `layout` 为 `compact_gather` 或 `indexed`，保留相同的 query 行数。QK/PV 共享 key 观测，gate/up/down 共享路由观测。 |
| `--workload` | 新模型或单 GEMM 可直接输入 `schema_version: 1` 的 `GemmWorkload` JSON。提供稳定 `workload_id` 和 `operators`，每项含 `op_id`、`stage`、`segment`、`layer_id`、`operator`、`category`、`subcategory`、`precision_label`、`dependencies`、`shape`。依赖引用同一账本的 `op_id`。提供 `useful_macs` 时会与形状复核。 |
| `--plan` | 可重复，首个为基线。文件含 `schema_version: 1`、`name`、可选 `format_proxies` 与 `rules`。规则使用 `select`、可选 `source` 和 `target`。选择器接受 `op_id`、`operator`、`category`、`subcategory`、`stage`、`segment`、`layers` 或闭区间 `layer_range`，同一条内条件取交集。空匹配和重叠规则会报错。 |
| `target` | 声明具体 `format_id`、`execution_path`、可选覆盖的 `weight_storage_format` / `activation_storage_format`，以及 `conversion`。转换 `kind` 为 `none`、`offline` 或 `online`，在线成本可提供每账本行的 `cycles_per_operator` / `bytes_per_operator`。离线/无转换的运行时成本为零，未知的在线周期留空。 |
| `--area-run` / `--array-model` | 配对提供 A 的输出目录和数组假设 JSON。可选 `--deployment-id`，默认用 A 的基线。配置提供 `dataflow: "serial_output_stationary"`、`context_slots`、可空 `feedback_cycles` / `buffer_bytes` / `read_bytes_s` / `write_bytes_s`，及 `initial_c: "zero"` 或 `"load"`。反馈周期至少为 DP 的 L。 |
| `--quality` | 可选，`schema_version: 1` 和 `records` 数组。用导出的完整 `plan_id` 关联，记录 `metric`、`direction`（`higher` 或 `lower`）、`reference_value`、`candidate_value`、`max_degradation`、`dataset`、`protocol`、`model_revision`、`quantizer_revision`、`provenance`。 |

`routing_policy` 选择 `balanced` 或 `hot_experts`。后者是所有 token 路由至同一 top-k 专家集合的敏感性场景。V4.1 native Candidate Indexer 可用 `candidate_policy: "pinned_blocks"` 或 `"upper_bound"`，简化 prefill 用前者。默认 generic FP8/FP4 标签保留未解析状态，用户可显式设定例如 `"format_proxies": {"fp8": "mxfp8_e4m3"}` 做敏感性分析。W4A8 的原始权重和激活格式分开保存，必须有显式执行规则才能解析到同格式 DP。

### Shape contract

每条记录粒度为 `stage × segment × layer × op_id`。模型默认保留已知的本层 GEMM 依赖和 KV 所有者。跨层控制和非 GEMM 中间步骤由下游调度器补足。

| `shape.kind` | 必填数据 |
|---|---|
| `dense` / `grouped` | 正整数 `m,n,k` 和可选 `repetitions`（默认 1）。各组独立占用输出 tile。 |
| `experts` | `n,k,tokens_per_expert`，每个非零专家是自己的 M 维。 |
| `ragged` | `m,fixed_dimension,axis,layout`，再加 `length_runs` 或 `key_rows`。`axis: "n"` 是 QK，`"k"` 是 PV。`length_runs` 的每条 `[first,last,count]` 代表从 first 到 last 的每个长度重复 count 次。参考矩形执行可以另给 `execution_length_runs`，保留逻辑有效算量和冗余算量。 |

## Outputs

| 文件 | 粒度与边界 |
|---|---|
| `workload.json` / `gemm_ledger.csv` | 算子账本、依赖、useful MAC/FLOP、来源和形状。完整稀疏和路由描述也导出到 `sparse_shapes.json` / `expert_histograms.json`。 |
| `precision_plans.json` / `precision_map.csv` | 方案×算子。存储、乘法、累加、scale、DP mode、转换和代理来源。 |
| `reference_diff.csv` / `precision_migrations.csv` | 参考/目标场景差异，以及固定工作量的逐算子精度变化。可比的 issued MAC、阵列周期和完成时间附前后差值。 |
| `workload_summary.csv` / `excluded_work.csv` / `coverage.json` | 逐精度/子类汇总、排除或未解项、精度解析率和阵列完成时间覆盖率。分母是同一账本全部 GEMM useful MAC。 |
| `operator_evaluations.csv` / `tile_services.json` | 方案×算子×指定部署。前者记录 useful/issued、尾部、反馈、I/O、转换、周期和时间。后者按每输出 tile 的 K 发射次数聚合，供多核调度消费。 |
| `quality_records.json` / `backend_validation.json` | 外部整方案质量状态，以及解析后端和校准状态。 |
| `manifest.json` / `summary.md` | 输入、源码与输出的 hash、版本、命令和运行摘要。CSV 空白表示该指标未知或不适用，JSON 使用 `null`。 |

阵列按同 K 步数的输出 tile 分波，每波最多使用 `context_slots` 个上下文，轮转发射、等待反馈并排空。首版使用本地 A/B 逐次读取、部分和驻留以及显式串行 I/O，无跨发射时间复用。由此分别给出 `shape_utilization = useful / issued`、`k_tail_utilization = 有效 K 容量 / native-K 容量`（按有效输出位置计）、`temporal_utilization = 发射请求数 × II / 服务周期`、`effective_utilization = useful / (峰值 MAC/cycle × 服务周期)`。本地传输起点是已可供读取的操作数，稀疏 gather 的时间位于该边界上游。完成时间须有缓冲、带宽、反馈和适用转换成本。整芯片调度、HBM/通信、非 GEMM、质量测量和 SCALE-Sim 校准分别由上层或独立流程提供。

## Python API

```python
from ratio_dse.compute_model import build_workload, resolve_plan, compare_plans, evaluate_workload
from ratio_dse.common import read_json

root = "ratio_dse/configs/compute/"
workload = build_workload(read_json(root + "v41_prefill.json"))
base = resolve_plan(workload, read_json(root + "adapter_plan.json"))
target = resolve_plan(workload, read_json(root + "grouped_o_down_fp8.json"))
changes = compare_plans(workload, base, target)
# evaluate_workload(workload, target, deployment, profile, array_model) uses A's JSON records.
```
