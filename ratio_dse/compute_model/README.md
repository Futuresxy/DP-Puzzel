# 任务 B：DeepSeek GEMM 工作量与精度相关计算模型

日期：2026-11-12（Asia/Shanghai）；状态：待实施。负责目录为 `ratio_dse/compute_model/`，遵守 [共用合同](../docs/contracts.md)。首轮内置 V4/V4.1 系列 Attention/MoE prefill；保留 decode 接口但单独验收。其他模型由开发者实现 adapter。

## 执行指令

> 在 DP-Puzzel 中实现任务 B。先读根 AGENTS.md、ratio_dse 共用合同及本页。复用并核验 paper/scripts/workloads.py、deepseek_v41.py 的计算规则，建立保留 GEMM 形状、稀疏描述、专家分布和执行精度的账本；实现按 native K 分模式的 tile/利用率/周期评价与 precision plan 接口。先交付透明的解析后端，再按明确版本与数据流适配接入 SCALE-Sim 参考后端。完成本页输出和独立验收。只统计/模拟 GEMM，不运行大模型量化训练，不写阵列 RTL，不把参考模型周期当项目芯片实测。

## 输入与复用

- A 的 HardwareProfile/Deployment（或同 schema 的 synthetic fixture）；使用模式 native K、L/II、m/n、buffer/接口和反馈假设。
- 已有 `paper/data/inputs/models/` 配置及 `paper/scripts/deepseek_v41.py`、`workloads.py`、`costs.py`、`precision_migration.py`；输入 hash 和来源版本固定。
- `target_native_20261112` 按用户指定精度映射生成；`reference` 保留现有执行分支，逐项解释差异。已有 V4.1 ratio=2 Global-KV FP32 分支不能被无声改成 BF16。
- batch、context、past/query tokens、prefill schedule、cache reuse、routing 分布/假设、格式映射、迁移白名单、quality records。
- 先复用公式，不能只沿用 FLOP 汇总：现有有些记录是有效稀疏 pair 或总 expert assignment，必须恢复可执行的 GEMM/tile 描述。

## B1 工作量与算子映射

- [ ] 建立四类 GEMM 与 Indexer 子类的稳定 op_id；明确用户名与代码名映射，如 Grouped O-down=`o_group`、O-up=`o_final`。
- [ ] 按 layer、segment、QK/PV、SWA/CSA、Full/Candidate Indexer、expert gate/up/down 保留记录。V4 的 HCA 等差异按各自配置处理，不套用 V4.1。
- [ ] Dense/grouped GEMM 输出 M/N/K、次数；attention 输出 ragged 每行有效 key 数/区块集合的紧凑描述。QK 与 PV 分别构建矩阵，二者 K 方向不同，不可用同一形状替代。
- [ ] 区分 useful sparse pairs、实际执行 block/tile、padding/冗余计算和 gather/索引搬运。不能用 dense 利用率乘一个全局稀疏率代表实际时间。
- [ ] Routed experts 输出每专家 token histogram；无 trace 时提供明确命名的均衡分配假设/可配置不均衡场景，守恒总 assignment=token×topk。禁止将不同权重的专家拼成一个大 GEMM 来抬高利用率。
- [ ] 保留 global/index KV 复用、缓存构建、CED 重放、prefill 段；不因同层名字相同重复计数或漏计。reference 重放与目标映射分别计算。
- [ ] 将存储、乘法、scale、累加格式拆开。W4A8 必须带执行路径；同格式 DP 若通过权重转换执行，记录转换成本与缺失状态。低位宽存储不直接归入 FP4 算力。
- [ ] 单列剩余 GEMM/FP32 和非 GEMM 排除项，给出分母与覆盖率。未知精度不强塞 H/Q/E。
- [ ] precision plan 精确选择算子/层/子类；只改精度时 useful MAC 守恒，字节、issued MAC、K 尾部和周期允许变化。质量值未知保持 null。

## B2 利用率与周期

- [ ] API 至少接受 workload M/N/K（或 ragged/expert descriptor）、m_array/n_array、native_k、II、latency、dataflow、buffer 与接口、C/D feedback/context 假设。
- [ ] 先实现 dense 原生 K tiling 账本：有用 MAC、发射容量、M/N/K 尾部。覆盖 K 小于/等于/超过 native K，禁止仅按位宽倍率缩放时间。
- [ ] 区分几何利用率、时间利用率及最终有效利用率；每个值写清分子/分母，稀疏有效 MAC 与 padding/重复工作可追溯。
- [ ] 以显式 issue 日程计算 fill/drain 和 RAW 等待；独立输出可交错隐藏反馈，能力取决于 context 数，不能因为 L8/II=1 就给同输出每拍反馈。
- [ ] 输入读、结果写、scale、转换分别计数。重叠仅在有缓冲/调度假设时启用，并输出时间线或可复算摘要。
- [ ] 输出 tile 服务记录给 C；B 不决定整芯片核心数，也不直接用核心数除单阵列时间。
- [ ] 未决数据流使用明确命名的解析场景；缺失关键条件时返回部分结果/下界，不能声称已校准。

## B3 SCALE-Sim 与 LLMCompass 适配

LLMCompass 的 Matmul 实现包含形状查表、解析快速路径及 SCALE-Sim 回退；SCALE-Sim 接受阵列配置和 GEMM M/N/K，输出周期、停顿、利用率及访问统计。[LLMCompass 源码](https://github.com/PrincetonUniversity/LLMCompass/blob/main/software_model/matmul.py) · [SCALE-Sim 官方说明](https://github.com/scalesim-project/SCALE-Sim)

两者为本任务的参考和候选依赖，不是已启用组件。本项目 m/n 个 DP 各自执行 native K 规约，与默认标量 MAC 脉动阵列并不等价。适配必须保留尾部与依赖，不能将整个模拟周期直接除以 native K，或只设置 MAC/cycle 就宣称精度利用率准确。

- [ ] 在 `dependencies/` 记录所选工具的完整 commit、许可证、用途、单位、补丁和获取命令；源码放 `.deps/`。选版未定时后端保持 disabled。
- [ ] 先写 mapping note，说明广播组、标量模拟阵列、原生 K、部分和、fill/drain 的对应和误差。无法对应的模式保留为 reference_systolic，不用于项目推荐排序。
- [ ] 在匹配的数据流子集对照解析账本、独立手工周期与 SCALE-Sim；其他模型差异分开报告。不得继承上游论文的误差数字作为本项目校准。
- [ ] cache key 包含形状、格式/native K、数组 shape、dataflow、带宽/容量、反馈、布局和工具版本。相同 M/N/K 的不同精度不能误用同一利用率。
- [ ] 确认当前使用的工具版本与所需特性兼容；本轮不引入整套 LLM 模拟、DRAM 仿真或工具自带功耗来替换 DP 实测。

## 必须输出的数据

每次 run 放在 `ratio_dse/results/<run-id>/compute/`：

| 文件 | 内容 |
|---|---|
| `workload.json`、`gemm_ledger.csv` | 逐模型/阶段/layer/segment/op 的形状、精度、次数、useful MAC/FLOP、来源 |
| `sparse_shapes.json`、`expert_histograms.json` | 可重建的稀疏结构/每专家分配，含真实或假设状态 |
| `precision_map.csv`、`reference_diff.csv` | 用户目标映射、参考映射、具体格式/执行路径、差异原因 |
| `workload_summary.csv`、`excluded_work.csv` | 四类/子类/格式汇总与覆盖率；排除量及原因 |
| `precision_plans.json`、`quality_records.json` | 迁移选择及外部质量参数；无数据时 unknown |
| `operator_evaluations.csv` | op×array config×plan：native K、useful/issued MAC、各利用率、周期/时间、字节、转换及模型状态 |
| `tile_services.json` | C 可读取的 tile 类型、数量、依赖、服务周期、模式和 I/O 摘要，避免导出海量重复 tile |
| `backend_validation.json` | 解析/手工/参考后端的对照、误差范围、未适配项 |
| `manifest.json`、`summary.md` | 输入/依赖 hash、命令、模型边界与可复现摘要 |

建议代码为 `workloads/`（V4/V4.1 adapters）、`precision.py`、`tiling.py`、`backends/`、`cli.py`，均在 compute_model 内；公共任务输入放 `ratio_dse/workloads/`，测试放 `ratio_dse/tests/compute/`。

## 验收

- [ ] 手算 dense/grouped/ragged QK/PV，各自在极小模型上核对矩阵乘加量与 tile 数；不能只测试实现同款公式。
- [ ] 对现有 reference workload 重放做逐项回归，任何改变由 reference_diff 解释；用户目标映射用另一组预期值，不能被强迫匹配旧精度统计。
- [ ] K=q-1/q/q+1 和非整倍数；m/n 尾部；短 decode 作为接口单例；精度迁移后 useful MAC 守恒而利用率可以下降。
- [ ] 相同 token 总量、不同 expert histogram 应保留不同执行形状；相同 sparse density、不同块分布不能被无条件视作同周期。
- [ ] 同输出 RAW 与独立输出交错的手工 timeline 对比；带宽/转换未知不会返回伪造的完整时间。
- [ ] 所有缓存按配置隔离、可删除后复算；没有 SCALE-Sim 依赖时可运行解析测试，并明确外部后端未完成。

## 交接

B 向 C 提供可重复调用的算子/tile 评价 API 和机器输出；质量预测、完整模型 adapter 和阵列 RTL 均不在本任务内。C 需要新 shape/迁移时调用 B，不复制一份 FLOP 或利用率公式。
