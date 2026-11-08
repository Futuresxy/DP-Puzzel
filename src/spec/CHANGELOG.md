> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.7.4；修改时间：2026-11-08 08:08:47 +0800；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 版本记录与当前索引

## 1. 相邻主要架构版本

| 版本 | 时间（+08:00） | 核心合同 |
| --- | --- | --- |
| v1.6 | 2026-11-06 | 外部复位改为同步低有效 rst_n；流水显式实例化公共 DFF；CModel/RTL/spec 命名统一。数值、默认 K16/28/40、L8/II=1 保持。 |
| v1.7 | 2026-11-07 | QE 专用前端与 E96/E128/Q64E128 混合顶层；保持 L8/II=1，物理后端扩为7/9源。 |

v1.6 → v1.7：~~仅多精度/E64 独立顶层~~ → 保留原顶层，增加 E96/E128/Q64E128 混合组装配、逐请求参与掩码、7/9 源规约和 QE 专用前端；保持 L8/II=1。

## 2. 验证与实施边界

v1.6 的验证记录见 [规范化验证](../../test/results/dp-style-v1.6.md)。旧 N12 综合报告仍对应其原 export ID；本次不以功能回归证明面积、时序或功耗。Chisel 与阵列未新增实现；混合组新增 CModel 和纯 Verilog，采用独立验证证据。

当前实现小修 v1.6.4：多精度 dp_lane_unpack 改为 A/B 紧凑 M/E/S 入口，内部完成配对特殊分类；新增 dp_lane_operand_unpack 保存原 S1 字段。尾数/指数 bank 直接选 M32/E20，移除 184 位 Number 展开接口。CModel、数值布局、S1/S2 边界和 L8/II=1 不变。沿用 rN 功能命名、就地 DFF 与完整语义排版；同步测试探针。代码对比与验收见 [紧凑解包验证](../../test/results/dp-compact-unpack-v1.6.4.md)。

## 3. 当前文件索引

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [README.md](README.md) | v1.7.1 | 汇总新版规格入口和生效范围 |
| [00-system-scope.md](00-system-scope.md) | v1.5.8 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.5.4 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.5.4 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.5.4 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.5.7 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.5.8 | 定义现用模型/RTL及未来实现的共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.5.5 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.7.3 | 维护整体架构与文档版本时间线 |
| [TEMPLATE.md](TEMPLATE.md) | v1.4.1 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.5.4 | 定义规格版本和历史修订规则 |
| [dp/README.md](dp/README.md) | v1.7.3 | 按模块与共用合同组织 DP 规格 |
| [dp/lane/README.md](dp/lane/README.md) | v1.7.1 | 定义 lane 规格目录与计算边界 |
| [dp/lane/dp_lane_E.md](dp/lane/dp_lane_E.md) | v1.7.2 | 讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合 |
| [dp/lane/multiplier-sharing.md](dp/lane/multiplier-sharing.md) | v1.5.4 | 定义尾数乘法器共享和模式路由 |
| [dp/lane/shifter-sharing.md](dp/lane/shifter-sharing.md) | v1.5.4 | 定义固定物理移位器的 mux 复用 |
| [dp/lane/unpack.md](dp/lane/unpack.md) | v1.6.4 | 定义固定 E/M/S 解包数值布局 |
| [dp/group/README.md](dp/group/README.md) | v1.7.1 | 定义 group 规格目录与计算边界 |
| [dp/group/dp_group_E.md](dp/group/dp_group_E.md) | v1.7.2 | 讨论 E16 定点组规约及兼容的 group 输出 |
| [dp/group/scale.md](dp/group/scale.md) | v1.5.5 | 定义 scale 统一解包和 bias 处理 |
| [dp/group/shared-align.md](dp/group/shared-align.md) | v1.5.4 | 定义分组共享对齐微架构 |
| [dp/dptop/README.md](dp/dptop/README.md) | v1.7.1 | 定义 DP 顶层规格目录与后端边界 |
| [dp/dptop/control.md](dp/dptop/control.md) | v1.6 | 定义 DP 逐请求控制与有效位推进 |
| [dp/dptop/global-align.md](dp/dptop/global-align.md) | v1.5.4 | 定义 scale 后实际指数检测与合并对齐 |
| [dp/dptop/independent-align.md](dp/dptop/independent-align.md) | v1.5.4 | 记录独立移位对齐对比方案 |
| [dp/dptop/interface.md](dp/dptop/interface.md) | v1.6 | 定义 DP 顶层和模块接口 |
| [dp/dptop/layout-and-scales.md](dp/dptop/layout-and-scales.md) | v1.5.4 | 定义 DP 容量与输入布局 |
| [dp/dptop/module-hierarchy.md](dp/dptop/module-hierarchy.md) | v1.6.4 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/dptop/pipeline.md](dp/dptop/pipeline.md) | v1.6 | 定义分组共享 DP 的流水候选 |
| [dp/common/numeric-layout.md](dp/common/numeric-layout.md) | v1.5.5 | 推导逐级位宽和统一对齐坐标 |
| [dp/common/special-values.md](dp/common/special-values.md) | v1.5.4 | 定义浮点分类与特殊值传播 |
| [dp/common/stage-formats.md](dp/common/stage-formats.md) | v1.5.4 | 列出每级数值出口的定点格式与指数范围 |
| [dp/implementation/cmodel.md](dp/implementation/cmodel.md) | v1.6 | 定义 DP CModel、模块映射及共用测试接口 |
| [dp/implementation/resource-accounting.md](dp/implementation/resource-accounting.md) | v1.5.6 | 定义可统计的功能模块边界 |
| [dp/implementation/verilog.md](dp/implementation/verilog.md) | v1.6.4 | 定义手写 RTL 实现映射及验证合同 |
| [dp-group/README.md](dp-group/README.md) | v1.4.1 | 定义广播计算组规格 |
| [tensorcore/README.md](tensorcore/README.md) | v1.4.1 | 定义 TensorCore 阵列规格 |

## 4. 混合扩展实现合同

| 文档 | 固定版本 | 评审范围 |
| --- | --- | --- |
| [混合顶层](dp/dptop/mixed-precision-expansion.md) | v1.7.3 | 三种扩展装配、输入布局、屏蔽、MAX/树、L8 与验证计划 |
| [QE lane](dp/lane/dp_lane_qe.md) | v1.7.3 | Q4E8 的紧凑解包、窄乘法和原 Q/E 流水 |
| [QE group](dp/group/dp_group_qe.md) | v1.7.3 | Q8E16 组和、无符号 scale 与兼容 S5 token |

CModel 验证见 test/results/mixed-cmodel-v1.7.md；RTL 验证和本轮 DC 使用各自的新快照与回执。

## 5. v1.7.2 优化方案修订

按现有 N12 综合面积分解补充 [混合顶层优化约束](dp/dptop/mixed-precision-expansion.md#10-独立面积优化版本与验收)，将 QE 固定字段解包、分类/符号寄存压缩、E 符号压缩及扩展源整数选择裁剪分别放入所属模块文档。明确扩展仍支持 NVFP4/HiF4，原四组保留 INT8；记录 55%–65% 为目标，不是已实现收益。S3 pair 前移和小系数乘法作为待验证候选，现有流水和数值合同不变。修正 E lane 残留的复位极性说明为同步低有效 rst_n。

v1.7.2 为优化方案修订；当前 v1.7.3 已实现独立优化顶层、固定字段 QE 解包和 S1 配对摘要，并静态裁减扩展源整数选择。保持原顶层默认实现、全部 Q/E 子型及 L8/II=1，S3 pair 前移和小系数乘法仍未实施。CModel 复用位精确算法并增加 profile 别名；新旧 unpack 319488 次对照、两顶层完整回归通过，见 [功能验收](../../test/results/qe-area-opt-v1.7.3.md)。独立 N12 TT/1GHz 综合与 hold 修复已通过，见 [最终比较](../../hw/dc_syn/records/qe_area_opt_n12_1000mhz_20261108.md)。面积 28191.89 µm²，相对原基础 DP 增长 66.53%，用户已接受本轮约 66% 增幅；不再为原 55%–65% 区间追加 RTL 修改。

## v1.7.4 四组低精度装配

增加 [E64/Q32E64 独立顶层](dp/dptop/low-precision-tops.md)，复用 E/QE group 和五源后端；容量、合法模式由静态配置限定，数值与 L8 合同不变。验证与综合独立记录，不继承旧快照验收。
