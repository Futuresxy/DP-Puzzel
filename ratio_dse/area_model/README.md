# 任务 A：面积与核心部署模型

日期：2026-11-12（Asia/Shanghai）；状态：待实施。负责目录为 `ratio_dse/area_model/`，共用 [数据合同](../docs/contracts.md)。本任务输出可由 B/C 直接读取的成本与部署数据，不运行 RTL/EDA，不计算模型工作量。

## 执行指令

> 在 DP-Puzzel 中实现任务 A。先阅读根 AGENTS.md、ratio_dse/README.md 和共用数据合同。导入当前九种目标配比的可用硬件证据，在 area_model 下实现成本校验、面积预算、等阵列规模与等每核输入带宽的部署枚举。完成本页规定的 JSON/CSV、独立小例验收和复现入口。缺失 profile 保留 null/状态，不插值、不套用历史 PETile。保护其他任务未提交改动，不创建或删除分支，不修改 RTL、论文结果或重跑 EDA。向任务 C 交付真实产物及其 hash。

## 输入

1. 显式选择的当前 DC/功耗记录及 export/验证引用，以 `hw/dc_syn/records/README.md`、`hw/power/records/README.md` 为发现入口。实现导入器后将选择清单固定为路径+hash，不能每次自动读“最新”。
2. 逐格式 native K、L/II、输入和 scale 布局、支持能力来自对应 spec/config/export；不只读配比字符串。
3. 场景配置：N0=36、alpha=0.30、基线 profile、arrays_per_core、基线 m/n、合法 shape 集、广播/复用、格式集合、带宽预算或其推导规则、频率、外围成本策略。
4. 实验参考 shape 必须显式命名来源；旧论文 16×16 可作为重放配置，不能替换当前架构 spec。默认无额外 SRAM/互连测量，不能伪造其成本。

## 设计与待办

- [ ] 建立 HardwareProfile/ModeProfile、ArrayScenario、Deployment schema 与校验器；由 native K/II 核对九种标签，最后两种为 H16Q96E192、H16Q128E256。
- [ ] 检查面积/功耗是否同一设计证据、PVT、频率和兼容版本；保留测量窗口、活动源、动态/漏电/总功耗及产物可用状态。审计当前源码与被测快照的区别，不要求被测结果假装匹配正在修改的源码。
- [ ] 缺失某种功耗不阻止面积分析；时序/电气失败不能进入目标频率已通过集合。面积有证据、功耗缺失的候选保持部分有效。
- [ ] 实现基线外围推导、整数核心部署、面积剩余和每模式峰值。每个场景报告基线是否回到 36 核。
- [ ] 等阵列分支固定全部候选的阵列 m/n 及每核阵列数；报告逐模式输入需求增长和是否满足另行指定的供数条件。
- [ ] 等输入带宽分支在合法 m/n 集合内枚举、按相同模式集合检查；保留全部合法部署给 C。不能仅最大化单核吞吐后丢弃可能因整数核心数量而更好的全芯片配置。
- [ ] 根据广播拓扑计算唯一 A/B 供数份数，计入 scale、packing 和复用；输出带宽和本地容量需求单列。不要把端口总线宽直接当有用流量，也不要把每核输入带宽当 HBM 带宽。
- [ ] 提供 CLI/API、两个场景样例和结果摘要；生产数据从 hw 导入，合成测试数据置 tests/fixtures 并标记 synthetic。

建议文件拆分：`profiles.py`、`area.py`、`bandwidth.py`、`deploy.py`、`cli.py`；schema 放本目录 `schemas/`，配置放 `ratio_dse/configs/area/`。可合并小模块，避免通用框架膨胀。

## 必须输出的数据

每次 run 在 `ratio_dse/results/<run-id>/area/` 下交付：

| 文件 | 行粒度及必须内容 |
|---|---|
| `hardware_profiles.json` | 每 profile 一条，嵌套逐格式能力和功耗；包含证据来源 |
| `profile_modes.csv` | profile×format：native K、II、MAC/cycle、动态/漏电/总功耗、功耗状态 |
| `deployments.json` | Deployment 主对象，含 scenario 和完整 topology/config 引用 |
| `deployments.csv` | scenario×profile×合法 shape：m/n、阵列数、DP 数、核心数、各层面积、预算、剩余面积、可行性 |
| `deployment_modes.csv` | deployment×format：单核/全池峰值、A/B 输入需求、预算余量、输出需求、模式支持状态 |
| `missing_evidence.json` | 所有缺失/不兼容字段、受影响候选和允许完成的分析 |
| `manifest.json`、`summary.md` | 固定配置、hash、命令、模型版本、排除边界及结果摘要 |

图表由 C 统一生成。A 不需要输出虚构负载功耗或最终排名。

## 验收

- [ ] 手工小例验证 alpha 外围只推导一次，基线恰为 36 核，候选按 floor 部署；覆盖刚好容纳、差一点容纳和无法容纳一核。
- [ ] 检查面积不重复计数、µm²/mm² 与 mW/W 转换、多个阵列、模式互斥和零/非法参数。
- [ ] 独立计算广播前后供数，覆盖非整字节 FP4 与尺度块尾部；同一物理配置的多个模式都接受相同预算检查。
- [ ] 在一个小型合法 shape 集上穷举核对枚举结果，检验放大阵列不必提高固定面积下的总峰值。
- [ ] 所有生成 CSV/JSON 能由同一 manifest 重算；缺失九候选中的某个测量时仍导出完整候选状态列表，不宣称九种全部已测。

## 交接

A 拥有硬件与部署字段，B 只读取不重定义面积；C 通过 deployment_id 使用部署，不能再次估算另一套核心数。外部依赖不是本任务前置，纯 Python 标准库可先完成。
