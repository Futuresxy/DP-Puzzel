# 后续实施路线

## 当前路线：先完成新版整体 spec

2026-11-04 用户明确旧 DP 设计过时，新设计在根目录 `src/` 展开，共用测试在根目录 `test/`。旧 Chisel 已移至 `hw/legacy/`；历史记录保留，不能作为新版的默认结构或通过证据。

1. 从 [新 spec 索引](../src/spec/README.md) 逐项定义系统范围、数值语义、DP 微架构、接口、周期状态、Cube、参数与验收。已记录首批要求，其余合同继续逐项定义。
2. 整体规范闭合并经用户确认后，开始 CModel，验证位精确运算与周期行为。
3. 基于同一 spec 和 CModel 开发 Chisel 与独立手写 Verilog，在根目录 `test/` 中共用测试环境验证。
4. 明确新导出及签核门禁、工艺/PVT/时钟和负载后，接入 DC/功耗；当前不执行 EDA。

当前首批要求已写入 [spec](../src/spec/README.md)：TensorCore 为 16×4 个 DP，由四个 4×4 广播 DP-Group 竖直拼接，组内无脉动；DP 支持 FP16 基准 K4/K8/K16 和 TF32/FP16/BF16/MXFP8/6/4/NVFP4/HiF4/INT8，HiF8 暂不支持。精度目标为主浮点模式至少 25 位、MXFP4/NVFP4 35 位、HiF4 约 37 位并复用 NVFP4 通路；INT8 并行度等于 MXFP8。DP 不超过 8 级，目标 1.41 GHz，功耗优先、面积其次。尚无实现或验收结果。

### DP spec 闭合清单（CModel 前）

已确定当前主方案为 T2H4Q8E16 基本组、两个 T1H2Q4E8 lane；FP16 K4/K8/K16 对应 1/2/4 个基本组及 T2H4Q8E16 / T4H8Q16E32 / T8H16Q32E64。A/B/C 原子接收、scale/meta 携带、DP 内 FP32 C 合并、FP32 D 与无输出背压已写入 DP 接口/控制 spec。独立移位对齐保留为后续对比探索。

开始 CModel 前按依赖顺序逐项闭合：

1. **一次 DP 请求及跨请求 C**：C 是每笔独立 DP 点积的初始加数，还是通过下一请求的 C 做累积；是否需要 in/out last；DP 与上层如何避免连续累加的 C→D RAW。FP32 输出与“每请求一个 C”已有方向，累加流语义仍待确认。
2. **逐格式 scale 数值语义**：MXFP8/6 scale 格式和一值覆盖 32 项规则；MXFP4/NVFP4 scale 编码、乘法值域及 scale 与 dot 的应用顺序；HiF4 e1/e2 字段的位宽、表示和作用顺序。物理每 16 E 项拆组已确定，格式数值规则未定。
3. **定点 token 合同**：lane 部分和、基本组 token、跨组和、缩放结果及 FP32 C 各自的 sign/exp-or-binary-point/width。解释 25/35/约 37 位分别保留在哪个节点、是否含符号/增长/保护位；证明 E 的 4-bit fixed-point 融合是否对所支持编码无损。
4. **浮点编码与结果规则**：TF32 高 19 位各字段映射（复用 FP16 尾数、BF16 指数），FP16/BF16 特殊值；FP32 C/D 的 NaN/Inf/zero/subnormal 行为，RM 含义与可选舍入方向。
5. **请求/会话协议**：共享 A/B/C ready 的准确时序、scale/meta 与 A/B valid 的绑定；last 是否必需、什么时候可切换 mode、复位中止规则。固定 L=8 已确定为目标，INT8 快 2–3 周期是估计，精确 L 待算术合同收敛。
6. **共享 datapath 资源边界**：哪些乘法器位片、lane 移位、组内/组间加法器、scale 运算和 C/norm 逻辑跨 T/H/Q/E 共用；依构建 K 变化的树/宽度生成公式。此项完成后可形成可实现 RTL 结构映射。
7. **CModel 观察合同**：上述数值路径的逐周期状态和 valid/last 对齐；定义 S1–S8 可选 cutpoint 内容。数学高精度 reference 与位精确 cycle model 分开。

每次先只闭合一项、同步编辑对应 spec 和本清单，再推进下一项。第 1–5 项收敛后先开始 CModel 算术及周期模型；资源映射可与实现细化同步，但不能改变已确认数值/周期合同。完整 Cube 存储、组间调度和 EDA 参数不阻塞 DP CModel，仍留在 TensorCore spec 与后续阶段。

## 历史路线（保留供参考）

当前已完成定义/论文准备，用户已授权五族六profile的基础PE迁移与H/Q专用全局对齐。详见 [设计](../hw/spec/six-pe-design.md)。HQE/QE/E保留分级组织，公共输出F和11级周期统一，K/MN总18级；AlignmentConfig暴露四个对齐参数。后续优先完成完整数值/协议回归、验证门禁和EDA；阵列仍只调研讨论。

LAB1 已确定回到基础 PE（原 MidGroup）层组合，复用六种 profile，先完成 1:2:4 基线及 1:2:6、1:2:8、1:4:8 的 K/MN 比较流程。K 1:2:4 同时作为 MN 增配的共用基线，MN 只增加 E64 和 Q32E64 两种实验类型。当前不采用 PEGroup 层混合扩展，不改内部微架构；完整路线与参数构建示例见 [LAB1 实验说明](../hw/legacy/chisel_src/core/LAB1/four_ratio_design.md)。目标工艺/PVT/时钟、真实 workload 与 HiF4 规范版本仍待明确，完成 RTL 验证门禁后再进入 EDA。

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
