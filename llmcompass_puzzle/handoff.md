# LLMCompass-Puzzle 建模交接

更新：2026-11-13。研究代码和首批结果基于提交 `2d39aac`；本轮增加统一入口、迁移打包与清理。迁移包的 `handoff_manifest.json` 记录实际代码/数据 hash，`source_base_commit` 只是导出时的 Git 基点，文件 hash 才定义交付内容。

## 1. 接手后先做什么

**主线：在相同面积、功率与部署条件下，分析 Tensor 精度配比改变后，SM、vector、存储和带宽如何重新分配，才能得到实际负载收益。** 先解释瓶颈，再调整相关资源；不以扩大网格、增加 FP4 峰值或任意最低延迟点为目标。

当前完成的是 DeepSeek-derived **单个典型 MoE prefill 子层**，以及上游 A100 参考重放和芯片面积接入。尚不是完整 DeepSeek TTFT。接手者应先复现本批受控对照，再校准瓶颈，最后补完整 prefill 图。不要直接将单 MoE 时间乘层数宣布端到端加速。

## 2. 迁移到另一台机器

建议传输本目录 `exports/` 下的完整 `.tar.gz` 迁移包及同名 `.sha256` 文件。**仅复制裸 `llmcompass_puzzle/` 会缺依赖**；迁移包已经收集全部运行所需路径，并包含固定上游源代码和三个最终运行。它不是整个 DP-Puzzel 仓库，不含 PDK、EDA 工具、大型仿真波形、模型权重、旧试跑或本机虚拟环境。

```bash
# 在接收机器；文件名以实际收到的包为准
sha256sum -c llmcompass_puzzle-handoff.tar.gz.sha256
tar -xzf llmcompass_puzzle-handoff.tar.gz
cd llmcompass_puzzle_workspace

# 安装前先检查传输完整性；此步只用 Python 3.11 标准库
python3.11 -m llmcompass_puzzle export --verify .
python3.11 llmcompass_puzzle/setup.py
python3.11 llmcompass_puzzle/setup.py --check
llmcompass_puzzle/.venv/bin/python -m unittest discover -s llmcompass_puzzle/tests -v
```

推荐 Linux、Python **3.11**、至少数 GiB 内存；CPU 即可，主建模不需要 GPU/CUDA/PyTorch。依赖版本见 `requirements-cpu.txt`。安装默认需要 Python 包仓库网络，但迁移包中的 LLMCompass 已齐备，无需再次 clone。不要跨机器复制 `.venv`。

完全离线时，先在兼容 Python/操作系统/架构的联网环境准备 wheelhouse：

```bash
python3.11 -m pip wheel -r llmcompass_puzzle/requirements-cpu.txt -w wheelhouse
# 将 wheelhouse 同时传输；默认迁移包没有包含这些平台相关 wheels
python3.11 llmcompass_puzzle/setup.py --wheelhouse /path/to/wheelhouse
```

绘图单独使用 `requirements-figures.txt` 建环境，避免修改仿真环境的 NumPy 等版本。迁移检查只针对初始交付文件；开始修改模型后 hash 变化是预期的，应建立自己的 Git 版本和新运行目录。

## 3. “整合 LLMCompass”的边界

这里是一个统一工作区与命令入口，不是两套独立运行项目。固定的 LLMCompass 原始模块在 `llmcompass_puzzle/upstream/LLMCompass/`，项目适配器直接调用它们；DP 实测面积替代其原标量阵列成本。

| 上游能力 | 本项目整合方式 |
|---|---|
| 芯片成本：SM、ALU/RF、SRAM、L2、I/O/PHY | `backend.py` 调用原成本模型；`characterize.py` 替换 Tensor 面积，保留其他成本 |
| A100 GEMM/Softmax、SCALE-Sim mapper | `replay.py` 做 CPU 参考重放；Torch eager import 仅在内存中变为可选，不改上游文件 |
| 离散芯片参数搜索的思路 | `system_search.py` 枚举配比、SM、vector、HBM/L2 bundle，执行面积/容量/功率情景限制 |
| DeepSeek 混合精度、在线量化、功率和质量门禁 | 本项目新增 `moe_system.py`、`system_contract.py`、`quality.py`，不能称为上游已校准能力 |

上游版本：LLMCompass `2e015fd2ee750e6cad8d7152df52551e5b41ef20`；cost 子模块 `d98ac0586faaf63f8f4eac94aa7cd50f37421c1f`。原许可证随源码保留。Git 开发环境验证 revision+hash；迁移包没有 `.git`，改用 `.puzzle-source.json` 验证固定 revision、子模块版本和全部导出源码 hash。不会伪造 Git 仓库，也不解除来源检查。

为了保留证据锁的原路径和避免复制出第二套公共模型，迁移包保留精简的父目录结构：

```text
llmcompass_puzzle_workspace/
  README.md / handoff_manifest.json
  llmcompass_puzzle/          # 唯一建模入口：代码、配置、交接与研究文档
    upstream/LLMCompass/     # 固定原始源码、成本子模块及许可证
    upstream/quantization_sources/  # 固定 W4A8/W4A4 审查源码
    configs/                # 当前可执行配置及功率/质量接口
    records/                # 三阶段精简数值、测试、来源与研究发现
    runs/                   # 完整迁移包内的三个最终复现批次
    research/               # 外部精度质量证据，均有适用边界
    maintenance/            # 清理清单、迁移验证记录
  ratio_dse/                # 所需 common/formats/area importer，非第二条新搜索入口
  dependencies/             # LLMCompass/DeepScaleTool/量化源码锁
  hw/...                    # 小型实测成本记录、可用的 summary/audit
  src/spec/...              # 成本证据锁引用的 DP 合同
  paper/data/...            # 两个固定模型 config、工艺系数和来源
  paper/figures/            # 已有系统分析 PDF
  .skill/.../paper.mplstyle # 图形风格依赖
```

原仓库的 `ratio_dse` 主线没有删除或改写。迁移包只携带这里需要的子集；它不是复现原 `ratio_dse` 全部历史研究的发行包。

## 4. 当前输入、成本和结果

硬件输入在 `configs/characterize.json` 和 `ratio_dse/configs/area/dp_n12_20261112.lock.json`。九个 H:Q:E 配比为：

`1:2:4, 1:2:6, 1:2:8, 1:4:4, 1:4:8, 1:2:12, 1:2:16, 1:6:12, 1:8:16`。

成本依据是本项目真实 DP 的 N12 综合与功耗记录，不是用晶体管密度估计 DP。四份主来源：`hw/dc_syn/records/{v19_six_dp_20261110,five_expansions_20261112}.json` 与 `hw/power/records/{v19_six_architectures_20261110,five_expansions_20261112}.json`。锁内含 hash、原始工况、run/export/验证身份；迁移包也保留可取得的小型 summary/audit，但**不包含重新执行 EDA 所需的完整网表、SAIF、库和工作负载**。

迁移包同时包含 `hw/data/dp_latest_area_power_20261112.{md,csv}`：11 种已测硬件、30 个实测精度点的汇总入口。当前系统 DSE 使用其中九种多精度配比；完整成本资料保留，方便后续有依据地扩展候选池。

当前比较采用 1 GHz、L8/II1、每 SM 四个 4×4 DP 阵列。N12 通过 DeepScaleTool 的 14nm 代理换算到 N7：面积除 7.273，动态功率除 1.727 并按频率比例调整。N7 泄漏和时序未经验证；NVFP4 动态功率显式借用 MXFP4 代理。不能将这些写成 N7 芯片实测。

完整系统面积基准约 826.764 mm²，来自归一化 LLMCompass 成本情景，不是实物 A100 die 面积。physical SM 决定面积，enabled SM 和各阶段 active SM 决定服务能力。vector 档位联动 ALU/RF 成本；HBM/L2 使用成套容量/带宽配置，不能免费增带宽。

系统搜索输入为 `configs/moe_system_study.json`：两个固定 DeepSeek config、256/2048 全 EP 组 token、8 卡 EP、三种 routed-expert 方案（W4A8/MXFP4 W4A4/NVFP4 W4A4）、共享专家保持 FP8。shared 数量当前要求 1。量化融合开关、面积和功率情景在同一配置中；不读模型权重即可运行成本探索。

| 已完成阶段 | 可直接查阅的证据 |
|---|---|
| S1 上游接入、DP 面积替换、原始 A100 CPU 重放 | `records/s1-20261113/`；完整 `runs/s1-reference-20261113-v3/` |
| 系统资源、面积机会成本及功率/量化合同 | `records/system-audit-20261113/`；完整 `runs/system-audit-20261113-v4/` |
| 配比—资源—迁移受控 MoE 搜索 | `records/moe-system-20261113/`；完整 `runs/moe-system-20261113-v3/` |

## 5. 已有发现及其强度

详见 [MoE 结果](records/moe-system-20261113/README.md) 和 [主图](../paper/figures/llmcompass_moe_ratio_system.pdf)。以下都是 **V4-Flash、2048 token、NVFP4 routed experts、未限制功率的单 MoE 子层解析结果**：

1. 固定资源把 `1:2:4` 改为 `1:2:16`，FP4 峰值增至四倍，预测延迟只降低约 **0.03%**。专家 GEMM 仍受 HBM 限制，说明增加低精度供给可以饱和。
2. 保持 `1:2:4`，从 128/108 SM、vector 1×、HBM5 调整为 96/81 SM、vector 2×、HBM8，延迟降低 **21.1%**。两边都优化后，再改 `1:6:12` 额外降低 **5.0%**。合计约 25.1% 不能全部归功于配比。
3. 后一项新增收益的 **97.9% 来自仍使用 FP8 的 shared GEMM**。专家 A4 不意味着只需增加 E；残余 Q 需求仍可能决定增配价值。

250 W 情景改变资源和配比选择，但前列多个候选差距不到 1%，尚无证据认定唯一稳健最优。功率、量化服务率、局部供数/缓存与通信近似尚未校准；新代码测试通过不等于模型数值准确。

W4A4 已有公开实现。原始参考 W4A8 是片上展开 W4 后计算，不默认把整个 FP8 权重副本写回 HBM。NVIDIA NVFP4 W4A4 是独立实现路径。源码审查和成本规则见 [QUANTIZATION_AND_QUALITY.md](QUANTIZATION_AND_QUALITY.md)。

质量按整个 checkpoint+量化 recipe+评测协议绑定，不给“4 bit”统一损失常数。已有公开 BF16/MX/NV/HiF4 数据放在 `research/`，但缺少与本地完整方案严格匹配的评测，因此当前质量推荐为 **0**。`quality_policy.json` 空要求表示 unknown；成本最优和质量达标最优分表。接手时不得把 unknown 改成零损失。

## 6. 常用操作：统一入口

以下均在工作区根目录运行，输出路径必须不存在。旧的 `python -m llmcompass_puzzle.<module>` 和两个 shell 脚本仍兼容。

```bash
PY=llmcompass_puzzle/.venv/bin/python
$PY -m llmcompass_puzzle --help
$PY -m llmcompass_puzzle area --output llmcompass_puzzle/runs/new-area
$PY -m llmcompass_puzzle reference --output llmcompass_puzzle/runs/new-a100
$PY -m llmcompass_puzzle resources --output llmcompass_puzzle/runs/new-resources
$PY -m llmcompass_puzzle dse --output llmcompass_puzzle/runs/new-moe
$PY -m llmcompass_puzzle summarize --run llmcompass_puzzle/runs/new-moe \
  --output llmcompass_puzzle/runs/new-summary
$PY -m llmcompass_puzzle findings --summary llmcompass_puzzle/runs/new-summary \
  --output llmcompass_puzzle/runs/new-findings.json
```

`findings` 针对当前预定义主案例与对照计算；改变主案例/删除某个配比后，应相应调整它，不能套原结论。详细模型输入、时间/字节/功率单位与输出字段见 [MOE_STUDY.md](MOE_STUDY.md)。

主输出：`designs.csv` 为硬件，`candidates.csv` 为可行性与子层时间，`operator_breakdown.csv` 为阶段分解，`cost_only_selections.csv` 包含两个优化方向，`quality_constrained_selections.csv` 只保留质量达标候选，`manifest.json` 绑定来源。可重叠的资源服务时间不能相加当总延迟。

重新制作迁移包：

```bash
python3.11 -m llmcompass_puzzle export \
  --output llmcompass_puzzle/exports/llmcompass_puzzle-handoff.tar.gz
# 小型源码版可加 --without-runs，仍保留 records 的精简结果。
```

迁移包携带源代码和许可证，没有 Git 私有配置；如需继续开发原始 LLMCompass，本项目默认仍锁定原源码。应建立新的依赖版本/适配器并单独验证，不覆盖锁后继续引用旧精度结果。

## 7. 下一步开发顺序与验收

1. **先复现三个受控问题**：只换配比、两边同预算优化、固定硬件选择迁移。固定 workload/部署/frequency，对超预算点遮罩；将有意义的收益与近似并列区分。
2. **先校准已经暴露的瓶颈**：grouped GEMM 的 M/N/K 与尾块、W4 本地展开、独立/融合 A4 quant、shared FP8 GEMM、HBM/L2/EP 通信。拟合与持出 shape 分开。先做少量成对实验，不增加全维度网格。
3. **完善功率来源**：设备 idle、vector/转换、memory/link 的同边界系数；已有 DP 动态功率只是特定活动代理。逐阶段限制并发并重算时间，功率与能量分别输出。
4. **补完整 prefill 图**：attention、KV、mHC、Engram 等模块和生命周期、完整容量、上下文/batch/路由分布，再比较端到端。当前 MoE 子图没有 past-context 轴。
5. **绑定量化质量**：固定原模型和数值图、算法/校准、runtime、评测协议及 artifact hash，完整方案满足阈值后再做双向推荐。新增旋转/低秩分支必须同时加计算和存储成本。

新增计算能力却退化时，必须能归因于面积替代、功率并发、真实映射/供数或其他确实改变的条件。若旧执行路径仍可用且其他条件不变，最优映射应能退回旧路径；不能把启发式缺陷或粗 SM 网格跳变当成架构创新。

## 8. 清理与保留规则

本轮按用户要求删除 10 个被替代/失败的 run（约 248 MiB 文件数据），删除已经过时的 `configs/study_plan.json` 和 `EXPERIMENTS.md`；有价值的实验控制合入本文和 `MOE_STUDY.md`。旧方案“不考虑质量”的口径已被当前质量接口取代。Git 可查已删除脚本/文档历史，目录和数据 hash 清单见 `maintenance/cleanup-20261113.json`。

保留上述三个最终 run、全部 `records` 数值/证据、研究资料、必要原始成本记录和固定上游。`.venv` 保留在本机但不迁移；`__pycache__` 不进入迁移包。以后保持“一个已审查批次及其依赖 + 新批次”工作方式；删除前先检查 manifest/论文引用，不能按文件年龄一刀切。

历史 manifest 记录的是当时的代码/路径，不会随本轮重构改写；某些历史绝对路径仅用于追溯。新机器运行使用相对输入和实际输出路径，产生新 manifest。上次记录的 19 项测试是历史批次，新迁移验证以 `maintenance/handoff-validation.json` 为准。
