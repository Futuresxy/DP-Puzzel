# 任务 C：芯片模型与双视角 DSE

日期：2026-11-12（Asia/Shanghai）；状态：待实施，依赖 A/B。负责目录为 `ratio_dse/dse/`，遵守 [共用合同](../docs/contracts.md)。将 area_model 与 compute_model 组合为统一评价器，分别固定硬件或固定模型搜索。

## 执行指令

> 在 DP-Puzzel 中实现任务 C。阅读根 AGENTS.md、ratio_dse 的共用合同和 A/B 接口，消费其真实部署与 GEMM/tile 数据，在 dse 下实现多核心执行、DP 计算功耗/能耗、质量约束筛选和两个搜索入口。先以可手算的小工作负载串通流程，再运行已有证据支持的 DeepSeek V4/V4.1 场景。输出逐候选、逐算子、Pareto 和敏感性数据及带来源的图表。禁止复制 A/B 的核心公式、虚构缺失功耗或质量值；不修改 RTL，不运行量化训练或替用户发布结果。

## 两个视角

| 视角/入口 | 固定输入 | 搜索变量 | 公平基线 |
|---|---|---|---|
| `model_adaptation` | 一个具体 deployment、模型结构与负载、允许格式及质量预算 | 算子类别/层/子类的 precision plan | 同一 deployment 的参考执行精度 |
| `chip_selection` | 模型、负载、precision plan、面积与供数条件 | 九种 profile 及合法阵列部署 | 同一场景的 1:2:4 deployment |

固定硬件必须固定核心数、阵列尺寸、频率和资源，不能在迁移后重新部署更多核心。固定模型的硬件搜索不允许同时改变精度来混淆收益来源。两种视角使用同一 evaluator，联合搜索留作显式后续扩展。

## 设计与待办

- [ ] 读取 A 的完整合法部署与 B 的工作量/precision plan；严格匹配版本、工况、mode 支持和单位，检查相同指标的硬件边界。
- [ ] 建立确定性多核调度：首轮算子顺序执行，同算子的独立 M/N tile 分发到核心/阵列；K 段在同一输出上下文保持依赖。记录 core/array 完成时间与空闲，不能把单核时间除以核数。
- [ ] 支持 grouped/expert/ragged 任务的合法打包与权重身份；是否允许并发不同专家/混合模式必须由配置说明，不能把共享模式峰值相加。
- [ ] 从 B 的 tile 数据汇总输入/输出与 buffer 需求；启用共享带宽时建模竞争，未启用则声明所假定的独立每核供数。端到端通信、softmax 等不偷偷加入 GEMM 数字。
- [ ] 汇总 array_service_time、GEMM 完成时间及活动/等待/空闲窗口。按范围分解，缺失必要转换或调度条件时输出下界或 partial 状态。
- [ ] 消费逐格式 active 动态/漏电测量，建立命名明确的 power policy；idle 和 stalled 状态单列。未知量为 null，保留可运行的 sensitivity policy，但不称真实 DeepSeek 功耗。
- [ ] 输出 DP 计算能耗与窗口平均功耗；外围和存储缺失时整芯片总功耗/能耗为 null。面积可以包含外围，功耗边界必须单独声明。
- [ ] 质量接口支持 PPL 增量上限、准确率下降上限及已有 eligible plan；记录数据集、模型/量化版本。多指标分别检查；未知方案不进入 quality-feasible 结果，不能将损失简单相加。
- [ ] 分开 `hardware_only_exploration` 与 `quality_constrained` 两种质量政策。前者允许 unknown 并明确条件性，后者严格筛选。无质量记录时给出 unresolved 清单，硬件收益分析继续完成。
- [ ] 按迁移白名单枚举四类/子类计划；不可默认所有算子可转 FP4。计算量守恒与跨格式转换由 B 验证。
- [ ] 分别给出最快、最低平均功耗、最低 DP 能耗及 Pareto；声明 objective set 和 scope，不以任意加权分数替代。缺少功耗的候选可参加延迟排名，但不能进入完整功耗/时间 Pareto。
- [ ] 敏感性扫描 batch/context、alpha、输入带宽、调度/idle 假设与用户给定的质量阈值；不凭空生成 quality degradation 曲线。
- [ ] 生成结果表、可复现矢量 PDF，数据与配置绑定；三角图仅代表指定形状/理想假设，实际模型结果保留算子利用率。

建议模块：`schedule.py`、`power.py`、`quality.py`、`evaluate.py`、`search.py`、`report.py`、`cli.py`。共同场景放 `ratio_dse/configs/dse/`，测试放 `ratio_dse/tests/dse/`。不内置通用整机模拟器，不重复实现 A/B。

## 必须输出的数据

每次 run 放在 `ratio_dse/results/<run-id>/dse/`：

| 文件 | 内容 |
|---|---|
| `candidate_evaluations.json`、`candidate_evaluations.csv` | 两视角的 deployment/plan、完整状态、面积、核数、峰值/有效吞吐、时间、平均功耗、能耗、质量值与基线收益 |
| `operator_breakdown.csv` | 候选×op：精度、算量、利用率、计算/停顿/转换时间、字节、能耗及未知项 |
| `schedule_summary.json`、`core_activity.csv` | 调度政策、关键完成时间、各核心活动/等待/空闲及模式占用；大型 trace 可选且忽略提交 |
| `precision_migrations.csv` | 迁移哪些算子、移动多少 FLOP、质量状态、迁移前后指标；总 useful FLOP 守恒 |
| `pareto.csv`、`selection_summary.csv` | 按 view/scenario/质量政策/objective set 分组的非支配集合和并列优选 |
| `sensitivity.csv` | 参数、候选指标及发生选择变化的边界；不预设单调性 |
| `rejections.json` | unsupported、missing_evidence、quality_unknown、quality_failed、budget_failed 等具体原因 |
| `manifest.json`、`summary.md` | A/B run/hash、输入版本、完整配置、单位、复现命令、校准与排除边界 |
| `figures/*.pdf`、配套 CSV | 部署/有效算力、算子利用率、两视角 Pareto 和迁移轨迹；不绘制架构图 |

候选 ID 至少区分 profile、shape、scenario、workload、plan、performance backend 和 power policy；重复候选合并规则可追溯。每个 run 都记录九候选的可用/缺失状态，不以有效子集冒充全九配比已验收。

## 验收

- [ ] 用手排日程验证 1 核、多核、tile 数少于核心数、非整倍数分配；工作量增加和资源增加的影响可解释，未使用核心未被忽略。
- [ ] 相同 H/Q/E 占比但不同 GEMM 形状能产生不同利用率/时间；该例证明没有退回只按 FLOP/峰值比较。
- [ ] 固定硬件迁移前后部署 ID 不变；固定模型选型时 precision plan hash 不变。
- [ ] 人工可核验的小集合验证 Pareto、相同值并列、单位一致、缺失指标分组排除。
- [ ] 给定一组 synthetic 质量记录，测试阈值边界、质量未知、一个指标通过另一个失败；不将 fixture 数字用于论文结论。
- [ ] 手算 activity/idle/leakage 时间窗验证能量与平均功率一致；改变 utilization 不会无条件线性缩放全部功耗。
- [ ] 至少一个已有 V4 和一个 V4.1 prefill 场景打通两视角；使用已有证据子集并列出缺失候选。质量数据未就绪时完成 hardware_only 探索及 quality_constrained 的 unknown 筛选，不伪造可行推荐。
- [ ] 从原始输入重新执行得到同一机器输出；图表数字由同一输出生成，不手填最优比例或收益。

## 完成与后续边界

本任务完成条件为两视角可复算、字段完整、缺失证据处理正确；不要求先解决质量预测或所有外部工具校准。九种真实成本全覆盖、目标模型量化质量测量和经过校准的芯片完成延迟各自作为后续里程碑报告。正式论文中的“已支持/已验证”按实际完成项更新。
