> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.6；修改时间：2026-11-06 12:06:08 +08:00；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 版本记录与当前索引

## 1. 相邻主要架构版本

| 版本 | 时间（+08:00） | 核心合同 |
| --- | --- | --- |
| v1.5 | 2026-11-05 | S5 使用 14×8 无符号 scale；主/E 共用兼容 group token 和 S6–S8。 |
| v1.6 | 2026-11-06 | 外部复位改为同步低有效 rst_n；流水显式实例化公共 DFF；CModel/RTL/spec 命名统一。数值、默认 K16/28/40、L8/II=1 保持。 |

v1.5 → v1.6：~~reset 高有效、功能模块内 always 保存流水~~ → `rst_n` 低有效、`ff_sN_sM_<field>` 保存流水。接口使用方需同步改接复位；CModel JSON reset 继续表示“请求复位”的软件事件。冻结 SystemVerilog 不迁移。更早变更从 Git 历史查询。

## 2. 验证与实施边界

v1.6 的验证记录见 [规范化验证](../../test/results/dp-style-v1.6.md)。旧 N12 综合报告仍对应其原 export ID；本次不以功能回归证明面积、时序或功耗。Chisel、混合组和阵列未新增实现。

## 3. 当前文件索引

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [README.md](README.md) | v1.6 | 汇总新版规格入口和生效范围 |
| [00-system-scope.md](00-system-scope.md) | v1.5.8 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.5.4 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.5.4 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.5.4 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.5.7 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.5.8 | 定义现用模型/RTL及未来实现的共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.5.5 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.6 | 维护整体架构与文档版本时间线 |
| [TEMPLATE.md](TEMPLATE.md) | v1.4.1 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.5.4 | 定义规格版本和历史修订规则 |
| [dp/README.md](dp/README.md) | v1.6 | 按模块与共用合同组织 DP 规格 |
| [dp/lane/README.md](dp/lane/README.md) | v1.6 | 定义 lane 规格目录与计算边界 |
| [dp/lane/dp_lane_E.md](dp/lane/dp_lane_E.md) | v1.6 | 讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合 |
| [dp/lane/multiplier-sharing.md](dp/lane/multiplier-sharing.md) | v1.5.4 | 定义尾数乘法器共享和模式路由 |
| [dp/lane/shifter-sharing.md](dp/lane/shifter-sharing.md) | v1.5.4 | 定义固定物理移位器的 mux 复用 |
| [dp/lane/unpack.md](dp/lane/unpack.md) | v1.5.4 | 定义固定 E/M/S 解包数值布局 |
| [dp/group/README.md](dp/group/README.md) | v1.6 | 定义 group 规格目录与计算边界 |
| [dp/group/dp_group_E.md](dp/group/dp_group_E.md) | v1.6 | 讨论 E16 定点组规约及兼容的 group 输出 |
| [dp/group/scale.md](dp/group/scale.md) | v1.5.4 | 定义 scale 统一解包和 bias 处理 |
| [dp/group/shared-align.md](dp/group/shared-align.md) | v1.5.4 | 定义分组共享对齐微架构 |
| [dp/dptop/README.md](dp/dptop/README.md) | v1.5.8 | 定义 DP 顶层规格目录与后端边界 |
| [dp/dptop/control.md](dp/dptop/control.md) | v1.6 | 定义 DP 逐请求控制与有效位推进 |
| [dp/dptop/global-align.md](dp/dptop/global-align.md) | v1.5.4 | 定义 scale 后实际指数检测与合并对齐 |
| [dp/dptop/independent-align.md](dp/dptop/independent-align.md) | v1.5.4 | 记录独立移位对齐对比方案 |
| [dp/dptop/interface.md](dp/dptop/interface.md) | v1.6 | 定义 DP 顶层和模块接口 |
| [dp/dptop/layout-and-scales.md](dp/dptop/layout-and-scales.md) | v1.5.4 | 定义 DP 容量与输入布局 |
| [dp/dptop/module-hierarchy.md](dp/dptop/module-hierarchy.md) | v1.6 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/dptop/pipeline.md](dp/dptop/pipeline.md) | v1.6 | 定义分组共享 DP 的流水候选 |
| [dp/common/numeric-layout.md](dp/common/numeric-layout.md) | v1.5.4 | 推导逐级位宽和统一对齐坐标 |
| [dp/common/special-values.md](dp/common/special-values.md) | v1.5.4 | 定义浮点分类与特殊值传播 |
| [dp/common/stage-formats.md](dp/common/stage-formats.md) | v1.5.4 | 列出每级数值出口的定点格式与指数范围 |
| [dp/implementation/cmodel.md](dp/implementation/cmodel.md) | v1.6 | 定义 DP CModel、模块映射及共用测试接口 |
| [dp/implementation/resource-accounting.md](dp/implementation/resource-accounting.md) | v1.5.5 | 定义可统计的功能模块边界 |
| [dp/implementation/verilog.md](dp/implementation/verilog.md) | v1.6 | 定义手写 RTL 实现映射及验证合同 |
| [dp-group/README.md](dp-group/README.md) | v1.4.1 | 定义广播计算组规格 |
| [tensorcore/README.md](tensorcore/README.md) | v1.4.1 | 定义 TensorCore 阵列规格 |
