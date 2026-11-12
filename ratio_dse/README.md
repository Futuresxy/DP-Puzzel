# DP-Puzzle 芯片算力配比与模型精度 DSE

面积与部署、DeepSeek GEMM 工作量与精度迁移已提供可运行的解析模型。两者可独立运行，也可通过 `deployment_id` 联用。任务 C 已加入多核解析调度、DP 功耗代理与双视角搜索。首轮结果和验证边界见 [DeepSeek DSE 报告](results/summaries/deepseek-dse-20261113/README.md)。

目标：以组合式 DP 的同工况硬件成本为依据，分析固定核心总面积与输入带宽条件下，DeepSeek V4/V4.1 的 Attention、MoE GEMM 负载与芯片算力配比的匹配关系。输出面积、计算功耗、GEMM 时间、利用率及派生能耗；支持固定硬件选择执行精度、固定负载选择硬件两种视角。模型质量代价先保留为外部参数与约束接口。

## Quick start

Run from the repository root with Python 3.11 or later. Both models use the Python standard library. The examples use committed evidence and model configs.

```bash
bash ratio_dse/run_examples.sh
python3.11 -m unittest discover -s ratio_dse/tests -v
```

`run_examples.sh [new-output-directory]` prints the output root. It runs both area constraints, three 256-DP SM layouts, a V4 workload-only example, a V4.1 precision comparison, and a synthetic GEMM with complete array-local timing. Each run emits JSON, CSV and a manifest with input, source and output hashes. Use `python3.11 -m ratio_dse.area_model --help` and `python3.11 -m ratio_dse.compute_model --help` for individual runs.

## 阅读与任务分配

| 入口 | 职责 | 交付后供谁使用 |
|---|---|---|
| [全文故事线](docs/storyline.md) | 论文定位、章节顺序、研究问题与证据范围 | 中文论文后续改写 |
| [共用接口](docs/contracts.md) | profile、部署、GEMM、利用率、质量和评价字段 | 三个任务共同遵守 |
| [任务 A：面积与部署](area_model/README.md) | DP 成本到整核部署，等阵列与等输入带宽两种约束 | B 的硬件输入、C 的候选集合 |
| [任务 B：计算与负载](compute_model/README.md) | DeepSeek GEMM 拆解、精度迁移、原生 K 利用率与周期 | C 的算子级评价 |
| [任务 C：芯片模型与双向 DSE](dse/README.md) | 多核调度、DP 功耗/能耗代理、固定部署迁移与多目标搜索 | 可复算结果、论文图表数据 |

面积和 GEMM 入口各自位于 `area_model/`、`compute_model/`。可复制的 JSON 在 `configs/`，回归在 `tests/`，运行目录默认写入 `results/`。任务 C 读取两者的 JSON 或 Python API。

## 当前确定的范围

- 九种 H:Q:E 配比：**1:2:4、1:2:6、1:2:8、1:4:4、1:4:8、1:2:12、1:2:16、1:6:12、1:8:16**。用户已更正最后一项，禁止继续使用早先误写的 1:8:12。
- H 以 BF16/FP16 吞吐归一化，Q/E 以 MXFP8/MXFP4 表示；底层逐格式保留能力，不将 TF32、MXFP6、NVFP4、HiF4 无条件合并成本。
- 内置 DeepSeek V4/V4.1 adapter，也支持导入规范化 GEMM 账本。prefill 为主要用例，decode 目前覆盖逐步账本和短场景回归。
- 参考预算为 36 个基线核心、基线 TensorCore 面积占比 30%；均可配置。30% 只用于推导基线外围面积，不强制候选保持相同比例。
- 等阵列规模、等每核本地存储到 TensorCore 输入带宽为两个独立场景。各场景中物理阵列配置固定，不能按运行精度临时改变阵列面积。
- 评价对象为 GEMM 集合。非 GEMM 算子、通信和完整推理质量预测不在首轮实现内；被排除的 GEMM 另列覆盖率。
- SCALE-Sim/LLMCompass 为拟接入的建模参考；固定版本、适配与校准完成前，不作为项目已验证阵列时序。
- 只新增软件分析模型，不构成阵列 RTL、EDA 重跑、量化训练或自动改写论文的授权。

## 输出与证据

每次执行在 `results/<run-id>/` 保存 manifest、输入 hash、配置、逐算子与候选表、缺失项和复现命令。所有模型结果初始为 `analytical_uncalibrated`，引用的 DP 测量单独标记；不能因使用实测 DP 面积而把整核时延/功耗标为 measured。

硬件输入从 [DC 当前索引](../hw/dc_syn/records/README.md) 和 [功耗当前索引](../hw/power/records/README.md) 显式选择、冻结来源。旧 PETile 17 配比和旧论文数据只作命名明确的历史对照，不补齐当前候选的缺失测量。

待决的阵列合同、带宽供给口径、混合输入格式和质量接口见 [共用接口](docs/contracts.md)；项目路线登记于 [roadmap](../docs/roadmap.md)。
