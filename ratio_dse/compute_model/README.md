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

## 建模架构与周期

```text
模型配置 + prefill/decode 场景 + 可选运行观测
  → 分层 GEMM 账本（M/N/K、专家分布、稀疏 key 和有用 MAC）
  → 精度方案（存储、乘法输入、scale、累加、转换）
  → 面积部署 + 单阵列 M/N + 每模式 native K/L/II
  → tile 发射量、部分和反馈、输入/输出字节与单阵列周期
  → DSE 按 SM、功率与本地端口约束分配 tile，汇总时间
```

当前后端是 **Python 解析周期模型**。`backend_validation.json` 将 SCALE-Sim 参考后端标为 disabled。我们的阵列由广播组组成，每个 DP 一次归约一段 native K，时序按本项目的 L/II 和反馈合同求得。[TensorCore 组织](../../src/spec/tensorcore/README.md#1-组织与坐标) · [解析后端](tiling.py#L16)

1. **切块。** Dense GEMM 的一个输出 tile 对应阵列 M/N，沿 K 发射 `ceil(K / native_k)` 次。账本分别统计有用 MAC 和含尾块的发射容量。分组、逐专家和 ragged QK/PV 各自建 tile，保留权重身份和稀疏形状。
2. **计算与反馈。** 部分和留在阵列的输出上下文。按相同 K 步数把独立 tile 分波，每波最多 `context_slots` 个输出，轮转发射。若同一输出的 C/D 反馈还未就绪，后续 K 段要等。每波还要计流水排空。DSE 默认取 8 个上下文、反馈等于 profile 的 L，当前完整 DP 为 L=8、II=1。以单个输出 tile、三段 K 为例，发射在第 0、8、16 拍，结果在第 24 拍就绪。更多独立输出可填入其间的发射槽。
3. **本地搬移。** 单阵列 CLI 用 `read_bytes_s`、`write_bytes_s`。每次发射读入按广播折算后的 A/B、scale、填充字节，单阵列可选读初始 C，最终 D 按逻辑输出元素计。DSE 则按每 SM 的本地端口建模，活跃阵列平分带宽，D 写回按完整输出 tile 计。默认 `write_read_ratio=1`，DSE 的缓冲假设为每阵列 64 KiB，检查一份发射输入和在途部分和能否驻留。核心池中最晚完成的阵列决定该 GEMM 的时间。
4. **完成时间。** 当前串行路径为 `T_read + T_array_service + T_write`，单阵列接口还可加给定的在线转换周期。带宽不足会拉长供数时间，保留硬件候选。这是汇总的 I/O 等待估计，逐拍 ready/valid、突发和 bank 冲突留待具体接口模型。当前 DSE 统计本地就绪的 GEMM 集合，HBM、上游 gather 和非 GEMM 在该边界之外。[DSE 端口与关键阵列](../dse/model.py#L35)

### A/B 驻留和 ping-pong

当前周期路径已计入同次发射内的空间广播。A/B **跨发射**的驻留复用仍按 1 处理，面积模型的 `a_temporal_reuse` 和 `b_temporal_reuse` 只用于满速需求估算。若固定 `(M tile, K slice)` 依次处理多个 N tile，可以把 A 连同 scale 留在驻留缓冲，在每次发射前只补 B；换 K 段或 A 被驱逐时再补 A。这需要明确发射顺序、缓冲容量和各输出的部分和依赖，才能把上游读次数降下来。

历史 `study` / `migration_selection` 及单阵列 CLI 保留 `serial` 汇总模型。新的 [joint_search](../dse/README.md#joint-hardware--workload-search) 使用同容量 `single_buffer` / `pingpong` 对照：一个输入 bank 存放一轮 native-K 对所有活跃输出上下文的 A/B 与 scale；第二个 bank 可在当前轮发射时预取下一轮。每一轮等待其 bank 全部 ready，再轮转发射各输出；缓冲到 DP 假定有独立的全 native 发射宽度端口，配置必须声明 `operand_delivery: "native_issue_width"`。每 SM 的活跃阵列均分 refill / write 带宽，分配贯穿该 launch，不随某阵列提前完成而借用空闲份额。

令 a 为本波上下文数，k 为 K 轮数，S 为每次请求的 A/B+scale 字节，D 为一个完整输出 tile 的 FP32 字节，b 为 bank 数，r/w 为分配给阵列的每周期读/写字节：

```text
可用上下文 = min(配置上下文数, floor(buffer_bytes_per_array / (b × S + D)))
所需容量 = a × (b × S + D)，b = 1 或 2
R = ceil(a × S / r)             # 首轮/每轮 refill
I = a × II                     # 一轮发射占用
W = ceil(a × D / w)             # 一波最终写回
single_buffer_stride = max(R + I, feedback)
pingpong_stride = max(R, I, feedback)
T_wave = R + (k-1) × stride + (a-1) × II + max(L, II) + W
```

这来自逐轮 bank 可重用时刻、refill 完成时刻和每个上下文 RAW 的递推；独立事件参考测试覆盖不同 K、II、L、反馈和带宽。第一轮装载、最后流水排空和 D 写回都保留。每波写完才开始下一波，写回与 refill 不重叠；不模拟跨波预取、每请求部分 ready 或 bank 冲突。`single_buffer` 也允许 refill 填进反馈等待，所以与历史的全串行汇总路径不同。

输出 `compute_s` 是无搬移的阵列服务时间，`read_s/write_s` 是对应关键阵列的端口服务量，`overlap_s` 是其在时间线中的重叠，满足 `seconds = compute_s + read_s + write_s - overlap_s`。双缓冲不减少读取字节；只在明确允许的时段隐藏等待。总容量相同可能减少双缓冲的累加上下文数，故不保证它总是更快。A/B 跨请求驻留仍未启用，联合入口要求时间复用系数为 1；今后要以张量身份、遍历顺序和实际驱逐记录扩展，不能把面积阶段的平均复用系数直接套入运行时。

### 当前芯片设计研究的精度边界

按当前研究范围，四种累计迁移方案作为输入情景，**不设置困惑度、准确率或精度阈值筛选**，联合结果标为 `quality_status: out_of_scope`。纯精度迁移保持模型形状和 useful MAC 总量，改变逐精度 MAC 分布、native-K 请求数、尾块浪费、输入字节及运行时间。量化算法和训练如何达到所需模型质量属于外部工作，不在这里假定已经解决。

转换计算仍是硬件工作，但本轮边界从预格式化 A/B 开始，因此没有额外在线量化/scale 生成时间；不能把 GEMM 时间解释成完整推理端到端时间。工作量模型输出解析与迁移账本；面积模型输出可安装的硬件；联合 DSE 才施加 SM 并发功率、端口、缓冲和调度约束。

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

利用率分四项报告。 `shape_utilization = useful / issued`，`k_tail_utilization` 按有效输出位置比较有用 K 与原生 K 槽位，`temporal_utilization = 发射请求数 × II / 服务周期`，`effective_utilization = useful / (峰值 MAC/cycle × 服务周期)`。完整时间需要相应的缓冲、带宽、反馈和转换成本。

## 可选的外部质量记录与转换成本

以下接口保留给后续社区接入，当前联合芯片设计实验不启用质量门槛。

- **模型质量作为可行性约束。** 用同一 checkpoint、量化方法、校准数据和推理协议实际运行完整累计方案，记录 PPL、任务分数及长上下文任务结果。按具体模型版本、量化器、数据集与 `plan_id` 绑定证据，再用 `max_degradation` 检查各项指标。路由和注意力的变化可能相互影响，应直接评估每个完整方案。当前 `unknown` 的方案可用于硬件收益分析，质量筛选结果只收录通过的方案。
- **离线和在线成本分开。** 离线权重校准、量化和打包按一次部署记录时间、能耗和存储。若要报告摊到每请求的部署成本，注明摊销请求数。在线激活量化、scale 生成、重打包、上游 W4A8 权重展开和可能的 KV 重编码，按发生的算子/数据边界记录额外周期、字节和能耗。同一份转换结果被多处使用时按实际发生次数计。
- **先用盈亏平衡预算判断值不值得测。** 以同一芯片上上一步的 GEMM 时间减本步 GEMM 时间，得到本步新增串行在线转换的最大时间预算。如果转换能与搬移或计算重叠，用额外暴露在关键路径上的时间比较。当前 [四方案 DSE](../dse/README.md#precision-migration--chip-selection) 还输出允许重新选芯片时的预算，及可选质量筛选。在线转换的真实值仍来自外部测量。

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
