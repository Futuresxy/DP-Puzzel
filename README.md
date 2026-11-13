# DAC 2027 · 多精度张量计算算力配比 DSE

**当前阶段：11 种 DP 的实现与硬件测量已形成可追溯结果。** 原六架构见[既有交付](hw/power/records/v19_design_report_20261110.md)；本轮新增 T8H16Q64E64、T8H16Q32E192/E256、T8H16Q96E192 和 T8H16Q128E256，均以原四个基础组扩展并保留 T8/H16 能力。[五种完整功能验证](test/results/five-expansions-final-v1.12-20261112.md)、[1 GHz DC](hw/dc_syn/records/five_expansions_20261112.md)及[15 点真实负载功耗](hw/power/records/five_expansions_20261112.md)全部通过，均为 L8/II=1。最新 11 种 DP 的面积与 30 个已测精度点汇总在 [hw/data 文档](hw/data/dp_latest_area_power_20261112.md)与[CSV](hw/data/dp_latest_area_power_20261112.csv)。更大原生 K 的 Q/E 输入已[导入本项目](hw/power/workloads/petile_extended/README.md)。当前维护 CModel 与纯 Verilog；SystemVerilog 冻结为历史参考，Chisel 与阵列尚未实施。

| 入口 | 内容 |
| --- | --- |
| [设计规范](src/spec/README.md) | 架构、接口、每级数值与资源共享 |
| [CModel](src/cmodel/README.md) | C++ 位精确 / 逐级周期模型与构建命令 |
| [手写 RTL](src/verilog/README.md) | 单 DP、参数化 Verilog；SV 仅作冻结的历史参考 |
| [共用测试](test/README.md) | Packed 数据、独立参考及回归 |
| [模型报告](test/results/cmodel-v1.4.md) / [RTL 报告](test/results/verilog-v1.4.md) | 精度、流水断点、周期协议与覆盖边界 |
| [面积与 GEMM 解析模型](ratio_dse/README.md) | 单 DP 到芯片峰值、DeepSeek 工作量账本、单阵列精度迁移和可复算示例 |

设计开发在 `src/`，功能验证在 `test/`，分析所用 RTL 快照、DC 与功耗在 [hw/](hw/README.md)。文档采用当前定义优先的排版，只有相邻两个主要版本的核心变更保留删除线；见 [维护规则](src/spec/document-control.md)。

## 历史项目背景与旧实现记录

以下 PE、配置和实验说明属于旧设计，不构成新版架构的默认合同。

面向 AI 芯片张量计算，研究 **BF16/FP16 : MXFP8/6 : MXFP4/NVFP4/HiF4** 的算力配比如何选择，以及不同物理实现对**面积、真实负载功耗和计算延迟**的成本收益影响。

系统应支持两类设计决策：在已有架构的面积余量内增配计算资源，以及在下一代芯片的面积/功耗预算内重新分配张量计算资源。结果应给出可行配置、成本与收益分解及 Pareto 前沿，而不是预设一种“最佳比例”。

历史实现为五族六种基础 PE 及参数化 K/MN 编排。 H/Q专用路径改为16/32路统一对齐，HQE/QE/E保留分级复用；PE_E_g2/g4输出坐标对齐。详见 [六种PE设计](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/six-pe-design.md)、[配置](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/configs/README.md) 和 [源码导航](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/README.md)。编译/结构及有限定向检查不等于完整RTL精度验证；尚无PPA或ratio_dse实现。

阵列扩展目前只做 [调研与方案讨论](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/array-design-discussion.md)：2×2 group 组内广播/组间脉动、L0 A/B/C、逻辑 M8N32 指令及 GEMM 调度。物理阵列规模参数化；方案待用户审核，尚未新增阵列代码。

进一步的 [OS 内部调度调研](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/os-array-scheduling-research.md) 聚焦一条指令如何拆成物理 tile，比较 L0C 反馈与 group 本地累加，并给出论文、逆向研究和公开 RTL 的依据。

[官方 Ascend C → MMAD ISA 分析](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/ascend-official-mmad-isa-analysis.md) 从官方 v9.1.0 样例追到实际编译的 IR、后端汇编和机器指令字，并结合 L0 容量推导 FP16 指令的 M/N/K 边界；这属于外部 ISA 编译研究，尚无芯片执行或数值验证。

## 两个核心部分

| 部分 | 范围 | 对外输出 |
| --- | --- | --- |
| hw | 单计算阵列或单计算核心的 RTL 快照、DC 面积/时序、真实负载功耗 | 经过验证且带来源的硬件特征与活动成本 |
| ratio_dse | 多核心、多阵列 AI 芯片，包含共享 HBM、核心内 L1/L0、映射与调度 | 芯片级 area / power / gemm_compute_latency 与配比权衡 |

芯片模型参照多个 SM/AICore 的组织方式，不默认复现某一厂商芯片。格式名称、共享缩放、累加与转换必须显式定义，不能简单按位宽比例推导面积或吞吐。

## 文件导航

    .
    ├── AGENTS.md              开发、RTL、EDA、Git 和清理规范
    ├── CONTEXT.md             项目领域术语
    ├── docs/
    │   ├── architecture.md    模块边界、职责、数据流
    │   ├── data-contracts.md  输入输出、单位、ID、证据和数据状态
    │   ├── experiments.md     配比、预算、目标函数与比较方法
    │   ├── development.md     分支、PR、日常同步、依赖和产物管理
    │   └── roadmap.md         实施顺序与待定事项
    ├── src/                  设计规格、CModel、Chisel、Verilog
    ├── test/                 数据、参考模型、RTL 测试和验证回执
    ├── hw/
    │   ├── rtl/               唯一 EDA 输入快照目录
    │   ├── dc_syn/            挂载 EDA 中的面积、时序分析
    │   ├── power/             真实负载活动与功耗分析
    │   └── characterization/  hw 向 ratio_dse 交付的硬件特征
    ├── ratio_dse/
    │   ├── configs/           芯片、预算、候选配比
    │   ├── workloads/         GEMM/任务依赖与精度可行性
    │   ├── src/               后续模型组件职责说明
    │   ├── tests/             后续模型校准与一致性验证
    │   └── results/           本地完整结果、受控提交的精简摘要
    ├── dependencies/          外部依赖来源和固定版本约定
    ├── paper/                 LaTeX 正文、模板、图表、引用和投稿资料
    ├── scripts/               后续公共流程入口的职责说明
    ├── .skill/                所有项目专用 skill 的唯一位置
    ├── .codex/                保留已有开发配置
    ├── ref_work/              本地参考工作，不提交
    └── .deps/                 按需获取的第三方源码，不提交

建议按 [术语](CONTEXT.md) → [架构与数据流](docs/architecture.md) → [数据契约](docs/data-contracts.md) → [实验定义](docs/experiments.md) 阅读，再按 [后续路线](docs/roadmap.md) 逐项明确设计。

远程仓库为 `git@github.com:Futuresxy/DP-Puzzel.git`。小改动直接提交到本地 `feat/dp-verilog-v14`。需要并行推进的大任务经用户同意建立分支，通过 PR 合入 `main`。规则见 [开发流程](docs/development.md)。
