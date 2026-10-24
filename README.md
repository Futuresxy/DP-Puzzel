# DAC 2027 · 多精度张量计算算力配比 DSE

面向 AI 芯片张量计算，研究 **BF16/FP16 : MXFP8/6 : MXFP4/NVFP4/HiF4** 的算力配比如何选择，以及不同物理实现对**面积、真实负载功耗和计算延迟**的成本收益影响。

系统应支持两类设计决策：在已有架构的面积余量内增配计算资源，以及在下一代芯片的面积/功耗预算内重新分配张量计算资源。结果应给出可行配置、成本与收益分解及 Pareto 前沿，而不是预设一种“最佳比例”。

**当前状态：项目定义、论文准备及 DC 自动化基础设施。没有硬件/芯片模型实现或实验结果。** 已搭建 [DC 综合入口](hw/dc_syn/README.md) 和 [项目 skill](.skill/dc-synthesis/SKILL.md)，仅完成软件检查；真实 DC 和功耗分析须在获准的本机挂载 EDA 环境验收，本次未执行。已准备 [paper 入口](paper/README.md)、IEEEtran 模板及学术润色 skill。

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
    │   ├── configs/           后续硬件参数集
    │   ├── chisel_src/        后续单阵列/单核硬件
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
