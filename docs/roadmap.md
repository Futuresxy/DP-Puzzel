# 后续实施路线

## 当前路线：先完成新版整体 spec

2026-11-04 用户明确旧 DP 设计过时，新设计在根目录 `src/` 展开，共用测试在根目录 `test/`。旧 Chisel 和相关记录保留在 Git 历史，不能作为新版的默认结构或通过证据。

1. 从 [新 spec 索引](../src/spec/README.md) 逐项定义系统范围、数值语义、DP 微架构、接口、周期状态、Cube、参数与验收。已记录首批要求，其余合同继续逐项定义。
2. 整体规范闭合并经用户确认后，开始 CModel，验证位精确运算与周期行为。
3. 基于同一 spec 和 CModel 开发 Chisel 与独立手写 Verilog，在根目录 `test/` 中共用测试环境验证。
4. 明确新导出及签核门禁、工艺/PVT/时钟和负载后，接入 DC/功耗；当前不执行 EDA。

当前首批要求已写入 [spec](../src/spec/README.md)：TensorCore 为 16×4 个 DP，由四个 4×4 广播 DP-Group 竖直拼接，组内无脉动；DP 支持 FP16 基准 K4/K8/K16 和 TF32/FP16/BF16/MXFP8/6/4/NVFP4/HiF4/INT8，HiF8 暂不支持。精度目标为主浮点模式至少 25 位、MXFP4/NVFP4 35 位、HiF4 约 37 位并复用 NVFP4 通路；INT8 并行度等于 MXFP8。DP 不超过 8 级，目标 1.41 GHz，功耗优先、面积其次。尚无实现或验收结果。

### E 类专用 DP 候选（2026-11-05）

当前多精度单 DP 的 CModel、两版 RTL 和 N12 DC 流程已建立；EDA 执行以 AGENTS.md 的本机授权为准。新增 [dp_lane_E](../src/spec/dp/dp_lane_E.md) 与 [dp_group_E](../src/spec/dp/dp_group_E.md) 仅讨论 MXFP4/NVFP4/HiF4 专用 E64 单元，保留现有多精度设计作比较。

待用户确认：采用 E0 的现有 S3/S4 切点，还是进一步将 HiF4 移位合并到 lane 树后；group 使用兼容 M31 还是紧凑 M22 接口。建议先 E0+M22，局部位宽精确压缩，S6 保留可配 40 位窗口及 FP32 C/D。方案确认后再开发专用 CModel/RTL、建立等价验证和同条件 PPA，当前不执行新综合或功耗实验。

### DP spec 闭合清单（CModel 前）

已确定 T2H4Q8E16 基本组、两个 T1H2Q4E8 lane，1/2/4 个基本组构成 FP16 K4/K8/K16。A/B/C 原子接收、DP 内 FP32 C 合并、无输出背压已写入接口；独立移位对齐留作后续探索。

~~本轮已收敛的边界：C 的来源/指令依赖由上层处理，DP 仅计算本笔缩放点积加 C；输入/输出 last 保留，末结果输出后才能切换 mode；全局复位统一取消在途。固定 E/M/S 解包已确定，T/FP16 为 I1F10、BF16 为 I1F7、Q 统一 E5M3/I1F3、E2M1 转 I3F1、HiF4 S1P2/e1 融合为 I2F2，保留 1-bit e2，块 scale 为 E6M2 bias=48。特殊值分类、NaN/Inf 传播及渐进下溢行为目标已写入 [解包](../src/spec/dp/unpack.md) 和 [特殊值](../src/spec/dp/special-values.md)。这些定义尚无实现验收证据。~~

**v1.2 当前定义：** C 来源/指令依赖归上层，DP 仅本笔 dot+C；v1.2 逐请求 datatype 控制，last 只透传，全局复位取消在途。A/B 首版同格式，各自带 datatype，scale E8M0/E4M3/E6M2；C raw32 传至 S5 再按 FP32/INT32 解包。既有固定 E/M/S 和特殊值目标保持，尚无实现验收。

**v1.1 架构进展（2026-11-04）：** 当前按 T1H2Q4E8→T2H4Q8E16→H16Q32E64（T8）的模块边界定义八级共享流水；S2 乘/指数并行、S3 幅值 RTZ、S4 lane 树、S5 scale 后 sign/magnitude、S6+C 幅值 RTZ、S7 全部规约、S8 RNE/INT32 回绕。E8M3 scale、bias 坐标、参数位宽和树深公式已补充；未来 Q/E/QE 仅在 S6 接入点规划，额外 1–2 级限于后续 profile。当前仍仅 spec，见 [模块层级](../src/spec/dp/module-hierarchy.md) 与 [数值布局](../src/spec/dp/numeric-layout.md)。

开始 CModel 前继续闭合：

~~1. **块 scale 与模式表**：明确 MX 的 E8M0、NVFP4 的 E4M3 是否作为本项目 scale 编码及特殊值合同，是否存在额外 per-tensor scale；定义 A/B 子型合法组合。HiF4 E6M2/e1/e2 已明确，不再重复待定。~~

~~1. **v1.1 更新：** 块 scale 编码与融合顺序已有 v1.1 合同；继续冻结 A/B 子型组合、负/非法 scale 处理与额外 per-tensor scale 的边界。~~

**v1.2 当前定义：** 首版 A/B 仅同格式及各自 datatype/scale 合法矩阵已确定；继续冻结非法 payload 的诊断范围、最终数值特殊边界。
~~2. **逐级定点数值合同**：为解包后乘积、lane 和、基本组和、scale 融合、跨组和及 C 合并写出 sign/width/exponent-or-binary-point；定义主浮点至少 25 位、FP4 35 位、HiF4 约 37 位的计数口径、第一对齐保留节点、增长位和 guard/sticky/舍入规则。E 元素解包无损不等于所有后续移位无损。~~

**v1.2 当前定义：** 逐级定点表已补 S1–S8 的 sign/width/F、r/alpha/A 和 C 对齐例子；继续审阅主浮点 25、FP4 35、HiF4 37 的误差与保留口径，不能以总线宽度直接充当精度证明。

~~3. **最终 FP32 转换**：冻结 RM 集合/默认值，NaN canonical 或 payload 选择，有符号零、正常/非正规及 overflow/underflow 边界；异常 flags 是否导出和 tininess 时点。不能用 IEEE 特殊值正确替代有限点积正确舍入证明。~~

3. **v1.1 更新：** RNE 已确认；继续冻结 NaN/canonical、零符号、渐进下溢与外部 flags/tininess 观察范围。

~~4. **INT8 数值与流水**：确定 signed/unsigned、C/D 整数编码及 overflow/saturation；保留乘法/规约/加 C，按省去浮点对齐/归一化/舍入后的具体树深决定延迟，不继续预设 L=5–6。~~

4. **v1.1 更新：** signed INT8、INT32 C/D、八级与回绕已确认；继续审查精确位宽界限和共用数据通路落位。
~~5. **周期/资源合同**：浮点目标 L=8，完成最大 K 下各级组合深度和资源共享边界推导；复核 II=1、原子 ready 表达式、首请求锁定模式和同步高有效全局 reset 的候选协议。时序约束仍是 1.41 GHz，当前不运行 EDA。~~

**v1.2 当前定义：** 周期/资源：当前全格式 L=8；C S5、逐请求控制及共享移位器 mux 结构已写入。继续检查 1.41 GHz 下的组合深度、原子 ready 和同步复位候选；按功能块建立面积/功耗追踪，当前不运行 EDA。

~~6. **CModel 观察合同**：定义统一配置、事务 API、周期采样边界及 S1–S8 cutpoint，包含 E/M/S 分类、特殊摘要、各级部分和、valid/last、模式/复位状态；数学高精度 reference 与位精确 cycle model 分开。~~

**v1.2 当前定义：** CModel 前定义语言/API/序列化配置，按各级数值表提供 trace，记录逐请求 datatype 与复位/valid/last；不再实现模式会话状态机。数学高精度 reference 与位精确 cycle model 分开。

~~每项先同步 spec，再推进 CModel；精确 INT8 延迟由其算术合同与切分决定。Cube 存储、取数/指令依赖、组间调度和 EDA 参数继续在上层定义，不作为单 DP 的 C 来源问题重复讨论。~~

**v1.2 当前定义：** 每项先同步 spec，再推进 CModel；当前浮点和 INT8 均 L=8。Cube 存储、取数/指令依赖、组间调度和 EDA 参数继续在上层定义。DP 接口、逐级数值、共享移位器和功能块统计见新版 spec，本轮不写实现。

## 历史路线（保留供参考）

当前已完成定义/论文准备，用户已授权五族六profile的基础PE迁移与H/Q专用全局对齐。详见 [设计](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/six-pe-design.md)。HQE/QE/E保留分级组织，公共输出F和11级周期统一，K/MN总18级；AlignmentConfig暴露四个对齐参数。后续优先完成完整数值/协议回归、验证门禁和EDA；阵列仍只调研讨论。

LAB1 已确定回到基础 PE（原 MidGroup）层组合，复用六种 profile，先完成 1:2:4 基线及 1:2:6、1:2:8、1:4:8 的 K/MN 比较流程。K 1:2:4 同时作为 MN 增配的共用基线，MN 只增加 E64 和 Q32E64 两种实验类型。当前不采用 PEGroup 层混合扩展，不改内部微架构；完整路线与参数构建示例见 [LAB1 实验说明](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/core/LAB1/four_ratio_design.md)。目标工艺/PVT/时钟、真实 workload 与 HiF4 规范版本仍待明确，完成 RTL 验证门禁后再进入 EDA。

阵列扩展进入调研讨论阶段，见 [阵列方案](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/array-design-discussion.md)。用户已确认逻辑 M8N32、物理阵列参数化，以及 FP4 K64/96/128/192/256、FP8 K32/64/96/128；L0 布局、调度、累加语义和首版配置待审核，当前不编写阵列代码。

指令内部的物理 tile 切分与 OS 状态机另见 [深入调研](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/os-array-scheduling-research.md)。当前按用户提出的原生 K 方向讨论：`K_inst=K_native(mode, config)`，单条指令仅切 M/N，软件用多条原生指令完成完整 GEMM 的 K。优先审核跨指令累加驻留位置、依赖/反馈路径、context 数量与排出结构；不再要求较小 K 单元在同一条指令内循环补足较大 K。

[Ascend 对照调研](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/ascend-cube-scheduling-research.md) 补充另一种边界：16³ Cube 基本粒度之上，单条 MMAD 可描述更大的 K，软件仍可跨指令切 K。原生 K 绑定是本项目候选约束，不是厂商统一规律；最终指令接口须结合此次对照审核。

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

当前六种 PE 的合同和默认参数已在 [六种PE设计](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/six-pe-design.md) 与 [参数 spec](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/config/Parameters.md) 明确，后续优先完成用户源码审查及 SV RTL 验收。其余系统/实验参数不填任意默认值。论文投稿日期与规则仍在 paper/submission 中维护。

## 六种 PE 后续验收

- 审查六个合法 profile、四个对齐参数、batch 固定格式，以及逐层 S/I/F、scale block 和 PE 11级 / K-MN 18级周期合同。
- 以独立 reference 验证 H/Q 全局 RTZ 与 HQE/QE/E 分级 RTZ，覆盖一般尾数/指数、scale、特殊值、严重抵消和参数边界，分别记录误差。
- 完成 K/MN 的 C/D 数值与完整 batch 握手、排空、气泡和复位回归。当前[有限定向检查](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/six-pe-checks.md)不能替代这些验收。
- 完成 export/hash 验证门禁后，再接入挂载 EDA 的 DC 与真实负载 power；位宽、流水和后续阵列优化另列可验证合同。
