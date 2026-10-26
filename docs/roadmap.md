# 后续实施路线

当前已完成定义/论文准备，用户已授权五族六profile的基础PE迁移与H/Q专用全局对齐。详见 [设计](../hw/spec/six-pe-design.md)。HQE/QE/E保留分级组织，公共输出F和11级周期统一，K/MN总18级；AlignmentConfig暴露四个对齐参数。后续优先完成完整数值/协议回归、验证门禁和EDA；阵列仍只调研讨论。

PE代码归属已按用户补充要求重整：H/Q完整链路直接在PE文件，取消其SubPE/PG；HQE/QE/E保留分级模块，PE专属计算从Utils移回。抽样新旧RTL等价与固定周期检查见[记录](../hw/spec/pe-code-locality-checks.md)，不替代后续完整精度资格验证。

阵列扩展进入调研讨论阶段，见 [阵列方案](../hw/spec/array_ref/array-design-discussion.md)。用户已确认逻辑 M8N32、物理阵列参数化，以及 FP4 K64/96/128/192/256、FP8 K32/64/96/128；L0 布局、调度、累加语义和首版配置待审核，当前不编写阵列代码。

指令内部的物理 tile 切分与 OS 状态机另见 [深入调研](../hw/spec/array_ref/os-array-scheduling-research.md)。当前按用户提出的原生 K 方向讨论：`K_inst=K_native(mode, config)`，单条指令仅切 M/N，软件用多条原生指令完成完整 GEMM 的 K。优先审核跨指令累加驻留位置、依赖/反馈路径、context 数量与排出结构；不再要求较小 K 单元在同一条指令内循环补足较大 K。

[Ascend 对照调研](../hw/spec/array_ref/ascend-cube-scheduling-research.md) 补充另一种边界：16³ Cube 基本粒度之上，单条 MMAD 可描述更大的 K，软件仍可跨指令切 K。原生 K 绑定是本项目候选约束，不是厂商统一规律；最终指令接口须结合此次对照审核。

| 阶段 | 交付 | 验收依据 |
| --- | --- | --- |
| 0 定义 | 范围、术语、职责、数据流、开发规则、paper 模板与 skill | 文档相互一致、来源可核验 |
| 1 数值与实验契约 | 格式版本、累加/舍入、基线、workload、预算 | 可判断精度正确性与比较公平性 |
| 2 单阵列/单核硬件 | spec、Chisel、统一 RTL 导出、SV testbench | 对指定配置的 RTL 精度与周期回归通过 |
| 3 EDA 与功耗证据 | 挂载环境 DC/时序、真实负载回放、功耗/profile | 来源、工况、活动和测量范围完整 |
| 4 芯片模型 | 多核心、存储、映射/调度、area/power/latency | 解析例与测量校准、独立验证误差 |
| 5 DSE 与论文实验 | 增配/重设计扫描、Pareto、消融与敏感性 | 关键数据可复现、结论范围明确 |

芯片模型可以先使用显式解析假设，但正式成本收益结论需要适用的硬件证据。各阶段独立分支/PR，论文结论随实验证据形成，不预填收益数字。

## 实施前逐项明确

1. BF16/FP16 累加与输出；MXFP8/6 编码变体与缩放；HiF4 的具体来源/版本。
2. 专用阵列、共享多模式单元或组合的候选范围；点积长度、阵列形状、流水和单核边界。
3. 工艺/PVT、频率、EDA 挂载入口与工具版本；当前不能直接运行。
4. 核心数量范围、L1/L0 共享、HBM 能力、L2/互连/控制/PHY 开销及 HBM/封装报告边界。
5. 训练/推理负载、GEMM 形状/权重、真实输入、质量约束、格式分配、数据起止位置。
6. 增配场景的基线/面积余量，重设计场景的预算；频率与存储是否参与优化。
7. CACTI 等依赖来源、固定版本、适用范围与校准方法。
8. 大型证据归档与保留策略、论文复现方式。

当前六种 PE 的合同和默认参数已在 [六种PE设计](../hw/spec/six-pe-design.md) 与 [参数 spec](../hw/spec/config/Parameters.md) 明确，后续优先完成用户源码审查及 SV RTL 验收。其余系统/实验参数不填任意默认值。论文投稿日期与规则仍在 paper/submission 中维护。

## 六种 PE 后续验收

- 审查六个合法 profile、四个对齐参数、batch 固定格式，以及逐层 S/I/F、scale block 和 PE 11级 / K-MN 18级周期合同。
- 以独立 reference 验证 H/Q 全局 RTZ 与 HQE/QE/E 分级 RTZ，覆盖一般尾数/指数、scale、特殊值、严重抵消和参数边界，分别记录误差。
- 完成 K/MN 的 C/D 数值与完整 batch 握手、排空、气泡和复位回归。当前[有限定向检查](../hw/spec/six-pe-checks.md)不能替代这些验收。
- 完成 export/hash 验证门禁后，再接入挂载 EDA 的 DC 与真实负载 power；位宽、流水和后续阵列优化另列可验证合同。

## 测试数据方案的分步确认

2026-10-24 用户将采集改为两个模型第一层（索引 0），已完成 [AI 负载采集和数据准备](../hw/test/data/README.md)：仅用 WikiText-2 test，Qwen2.5-3B q_proj 和 Qwen1.5-MoE-A2.7B 专家 3 的 down_proj；每个来源 A[4,768] / W[16,768]，各 49,152 MAC，合计 98,304 MAC/格式。保存九种编码量化和独立 dot+C0 的 FP64 golden，来源/数据 hash 与软件检查见 [摘要](../hw/test/data/ai-first-layer-summary.json)。权重按字节读取约 57.8 MiB，完整数据保留在 `hw/test/data/artifacts/`，未执行 RTL/PPA。

人工定向与固定种子随机数据的生成方案留待用户后续讨论。当前 `.mem`/manifest 已定义，golden 明确处于 PE 局部缩放域；后续优先明确 C/反馈、舍入与误差验收，然后实现文件驱动 SV testbench 和输出报告。完整 checkpoint 版本、采集池与 token/通道/K 索引已保存；数据准备的软件检查不能替代 RTL 验收。
