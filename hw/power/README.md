# 单阵列 / 单核心真实负载功耗

必须在当前机器挂载的 EDA 环境内执行。当前只定义真实硬件和真实负载的分析链，不运行商业工具，不生成或虚构功耗结果。

## 无 PrimeTime 的方案调研

2026-10-24 完成方法调研，仅新增文档，尚未检查本机功耗许可证或执行工具：

- [解决方案与验收要求](no-primetime-methodology.md)：按 Power Compiler 功能是否可用选择 DC/SAIF 或 OpenSTA，说明真实负载、时钟、毛刺、寄生与准确度边界。
- [参考项目审计与对比](reference-flow-audit.md)：核对 `Quant_LLM_Chip_Codesign/HW/power_analysis` 的当前实现、skill、时钟活动修正和输入数据来源。

建议先建立可追溯的综合后平均功耗流程；物理准确度的进一步提升依赖 CTS、寄生与时序活动证据。仅有 DC 软件不能证明功耗功能已获授权，使用 SAIF 也不会自动提升已有波形的准确度。

## 后续目录与数据链

| 后续位置 | 职责 |
| --- | --- |
| workloads/ | 真实负载/trace 的来源、精度、映射与采样元数据 |
| activity/ | VCD/SAIF 生成与转换规则；大波形不提交 |
| scripts/ | 工具驱动、活动覆盖检查和报告提取 |
| configs/ | 工况和窗口；私有库/挂载路径独立配置 |
| runs/ | 完整活动/功耗结果与临时文件，默认不提交 |

数据链：

1. 接收具体负载及 tile/精度配置，生成或读取可核验输入，记录 input hash。
2. 在已验证的同一份 RTL 上重放，核对数值结果和周期，划分 reset、warmup、active、stall、idle、drain 窗口。
3. 提取 VCD/SAIF，绑定 export、层次路径、timescale、时间窗口与数据分布。随机测试切换率不能冒充真实 workload 活动。
4. 读取匹配的综合 netlist、约束和工艺库；先完成适用的 RTL/netlist 一致性验证。使用 SDF 或寄生信息时记录其来源。
5. 在挂载 EDA 中分析 internal、switching、leakage 和 total；检查活动映射覆盖率及未注释节点。记录毛刺建模、寄生缺失等适用限制。
6. 将不同格式、操作模式及 active/idle 状态的测量值交给 characterization；芯片模型依据调度活动加权，并另计共享存储/互连等成本。

输出须带频率、电压、温度、工作负载、测量窗口和功耗边界。真实负载不同，不能直接复用一个“单核固定功耗”乘以核心数。未来功耗 skill 统一放根目录 .skill/。
