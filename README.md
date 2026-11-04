# DAC 2027 · 多精度张量计算算力配比 DSE

**当前阶段：重新定义多精度 DP / Cube 整体架构 spec。** 用户明确旧 DP 设计过时；先逐步写完并确认新 spec，再编写 CModel，之后开发 Chisel 和独立手写 Verilog，共用根目录 `test/` 验证。已写入 TensorCore 16×4、4×4 广播 DP-Group 和多精度 DP 的首批要求；详细 spec 继续完善，没有新版实现。

```text
src/
├── spec/       新架构唯一规格入口
├── cmodel/     位精确与周期模型，待 spec 确认
├── chisel/     Chisel 实现，待 CModel
└── verilog/    独立手写 RTL，待 CModel
test/          共用用例、数学参考、TB 与适配层
hw/legacy/     旧 Chisel 与历史构建定义，仅供参考
```

入口：[新设计](src/README.md) · [规格索引](src/spec/README.md) · [验证目录](test/README.md) · [历史归档](hw/legacy/README.md) · [重规划记录](docs/dp-cube-replan.md)。生成 RTL、DC 与功耗目录继续保留在 `hw/`。

## 历史项目背景与旧实现记录

以下 PE、配置和实验说明属于旧设计，不构成新版架构的默认合同。

面向 AI 芯片张量计算，研究 **BF16/FP16 : MXFP8/6 : MXFP4/NVFP4/HiF4** 的算力配比如何选择，以及不同物理实现对**面积、真实负载功耗和计算延迟**的成本收益影响。

系统应支持两类设计决策：在已有架构的面积余量内增配计算资源，以及在下一代芯片的面积/功耗预算内重新分配张量计算资源。结果应给出可行配置、成本与收益分解及 Pareto 前沿，而不是预设一种“最佳比例”。

**当前状态：五族六种基础PE及参数化K/MN编排。** H/Q专用路径改为16/32路统一对齐，HQE/QE/E保留分级复用；PE_E_g2/g4输出坐标对齐。详见 [六种PE设计](hw/spec/six-pe-design.md)、[配置](hw/configs/README.md) 和 [源码导航](hw/legacy/chisel_src/README.md)。编译/结构及有限定向检查不等于完整RTL精度验证；尚无PPA或ratio_dse实现。

阵列扩展目前只做 [调研与方案讨论](hw/spec/array_ref/array-design-discussion.md)：2×2 group 组内广播/组间脉动、L0 A/B/C、逻辑 M8N32 指令及 GEMM 调度。物理阵列规模参数化；方案待用户审核，尚未新增阵列代码。

进一步的 [OS 内部调度调研](hw/spec/array_ref/os-array-scheduling-research.md) 聚焦一条指令如何拆成物理 tile，比较 L0C 反馈与 group 本地累加，并给出论文、逆向研究和公开 RTL 的依据。

[官方 Ascend C → MMAD ISA 分析](hw/spec/array_ref/ascend-official-mmad-isa-analysis.md) 从官方 v9.1.0 样例追到实际编译的 IR、后端汇编和机器指令字，并结合 L0 容量推导 FP16 指令的 M/N/K 边界；这属于外部 ISA 编译研究，尚无芯片执行或数值验证。

## 两个核心部分

| 部分 | 范围 | 对外输出 |
| --- | --- | --- |
| hw | 单计算阵列或单计算核心的 spec、Chisel、RTL testbench、DC 面积/时序、真实负载功耗 | 经过验证且带来源的硬件特征与活动成本 |
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
    ├── hw/
    │   ├── spec/              数值语义、接口、周期、验收标准
    │   ├── configs/           PE 与 MN/K 顶层参数文件
    │   ├── chisel_src/        单阵列/单核硬件，当前为 PE 迁移源码
    │   ├── rtl/               唯一生成 RTL 存储位置
    │   ├── test/              Verilog/SystemVerilog 验证职责
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

远程仓库：git@github.com:Futuresxy/DP-Puzzel.git。所有新增功能先建分支、提交 PR 后合并；有代码变更的工作日至少一次 commit + push，重大架构/关键数据更新及时同步。规则见 [开发流程](docs/development.md)。
