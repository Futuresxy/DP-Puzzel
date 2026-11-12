> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.10；修改时间：2026-11-12 18:46:20 +0800；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 版本记录与当前索引

## 1. 相邻主要架构版本

|版本|时间（+08:00）|核心合同|
|---|---|---|
|v1.9|2026-11-09|E/QE 专用前端与三个混合顶层采用双指数 token、carry-save 合并和唯一 CPA；Q32E64 同步迁移。冻结 RTL、五份新 DC 和六架构 15 点功耗已完成，见[交付](../../hw/power/records/v19_design_report_20261110.md)。|
|v1.10|2026-11-12|新增 Q4 lane / Q8 group，四个基础组加四个 Q 组形成 T8H16Q64E64；保持 S5 token、L8/II=1 和 E64 容量。[完整功能回执](../../test/results/q-only-v1.10-20261112.md)通过，尚无 PPA；E192/E256 仅完成流水方案分析。|

v1.9 → v1.10：~~新增 Q 算力只能选择同时支持 E 的 QE 组~~ → 增加只支持四种 MXFP8/6 的 Q 组装配；T8H16Q64E64 扩展仅在 Q 请求参与，E 仍为 K64。原有六种架构不被替换：基础 dp_top 保持 [v1.8](dp/dptop/dp-top-v1.8.md)，既有混合与 Q32E64 保持 v1.9，独立 E64 保持原合同。

新合同：[Q lane](dp/lane/dp_lane_q.md)、[Q group](dp/group/dp_group_q.md)、[T8H16Q64E64](dp/dptop/t8h16q64e64.md)。[E192/E256 分析](dp/dptop/e192-e256-expansion-analysis.md)的 L9/L10 为待确认候选，版本号不代表增加流水已获批准。

## 2. 验证与实施边界

v1.6 的验证记录见 [规范化验证](../../test/results/dp-style-v1.6.md)。旧 N12 综合报告仍对应其原 export ID；本次不以功能回归证明面积、时序或功耗。Chisel 与阵列未新增实现；混合组新增 CModel 和纯 Verilog，采用独立验证证据。

紧凑接口基础 v1.6.4：多精度 dp_lane_unpack 改为 A/B 紧凑 M/E/S 入口，内部完成配对特殊分类；新增 dp_lane_operand_unpack 保存原 S1 字段。尾数/指数 bank 直接选 M32/E20，移除 184 位 Number 展开接口。CModel、数值布局、S1/S2 边界和 L8/II=1 不变。沿用 rN 功能命名、就地 DFF 与完整语义排版；同步测试探针。代码对比与验收见 [紧凑解包验证](../../test/results/dp-compact-unpack-v1.6.4.md)。

实现小修（2026-11-09）：多精度解包改为 `dp_unpack_atom` 固定字段直接生成 M16/E10/S4，移除活动通路的通用可变宽度解码与二次打包。分类在原始编码上判定，S1 分类存储和 S2 配对边界保持；CModel、数值、门控、L8/II=1 不变。[固定解包验证与综合对照](../../test/results/dp-fixed-unpack-20261109.md)限定本批验收为 dp_top。

文档小修 v1.7.8：按现用六种顶层重绘[可编辑嵌套架构图](dp/draw.io/README.md)，明确每组两条 lane、E 与多精度/QE 流水差异、扩展参与屏蔽和共享后端。仅修订图纸与导航，算术、接口、L8/II=1 和 RTL 不变。

## 3. 当前文件索引

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [README.md](README.md) | v1.10 | 汇总新版规格入口和生效范围 |
| [00-system-scope.md](00-system-scope.md) | v1.5.8 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.5.4 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.5.4 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.5.4 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.5.7 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.7.7 | 定义现用模型/RTL及未来实现的共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.7.7 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.10 | 维护整体架构与文档版本时间线 |
| [TEMPLATE.md](TEMPLATE.md) | v1.4.1 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.5.4 | 定义规格版本和历史修订规则 |
| [dp/README.md](dp/README.md) | v1.10 | 按模块与共用合同组织 DP 规格 |
| [dp/lane/README.md](dp/lane/README.md) | v1.10 | 定义 lane 规格目录与计算边界 |
| [dp/lane/dp_lane_E.md](dp/lane/dp_lane_E.md) | v1.9.1 | 讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合 |
| [dp/lane/multiplier-sharing.md](dp/lane/multiplier-sharing.md) | v1.8 | 定义尾数乘法器共享和模式路由 |
| [dp/lane/shifter-sharing.md](dp/lane/shifter-sharing.md) | v1.8 | 定义固定物理移位器的 mux 复用 |
| [dp/lane/unpack.md](dp/lane/unpack.md) | v1.7.1 | 定义固定 E/M/S 解包数值布局 |
| [dp/group/README.md](dp/group/README.md) | v1.10 | 定义 group 规格目录与计算边界 |
| [dp/group/dp_group_E.md](dp/group/dp_group_E.md) | v1.9.1 | 讨论 E16 定点组规约及兼容的 group 输出 |
| [dp/group/scale.md](dp/group/scale.md) | v1.8 | 定义 scale 统一解包和 bias 处理 |
| [dp/group/shared-align.md](dp/group/shared-align.md) | v1.8 | 定义分组共享对齐微架构 |
| [dp/dptop/README.md](dp/dptop/README.md) | v1.10 | 定义 DP 顶层规格目录与后端边界 |
| [dp/dptop/control.md](dp/dptop/control.md) | v1.6 | 定义 DP 逐请求控制与有效位推进 |
| [dp/dptop/global-align.md](dp/dptop/global-align.md) | v1.9.1 | 定义 scale 后实际指数检测与合并对齐 |
| [dp/dptop/independent-align.md](dp/dptop/independent-align.md) | v1.5.4 | 记录独立移位对齐对比方案 |
| [dp/dptop/interface.md](dp/dptop/interface.md) | v1.9.1 | 定义 DP 顶层和模块接口 |
| [dp/dptop/layout-and-scales.md](dp/dptop/layout-and-scales.md) | v1.5.4 | 定义 DP 容量与输入布局 |
| [dp/dptop/module-hierarchy.md](dp/dptop/module-hierarchy.md) | v1.9.1 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/dptop/pipeline.md](dp/dptop/pipeline.md) | v1.8 | 定义分组共享 DP 的流水候选 |
| [dp/common/numeric-layout.md](dp/common/numeric-layout.md) | v1.8 | 推导逐级位宽和统一对齐坐标 |
| [dp/common/special-values.md](dp/common/special-values.md) | v1.8 | 定义浮点分类与特殊值传播 |
| [dp/common/stage-formats.md](dp/common/stage-formats.md) | v1.8 | 列出每级数值出口的定点格式与指数范围 |
| [dp/implementation/cmodel.md](dp/implementation/cmodel.md) | v1.9 | 定义 DP CModel、模块映射及共用测试接口 |
| [dp/implementation/resource-accounting.md](dp/implementation/resource-accounting.md) | v1.5.6 | 定义可统计的功能模块边界 |
| [dp/implementation/verilog.md](dp/implementation/verilog.md) | v1.8 | 定义手写 RTL 实现映射及验证合同 |
| [dp-group/README.md](dp-group/README.md) | v1.4.1 | 定义广播计算组规格 |
| [tensorcore/README.md](tensorcore/README.md) | v1.4.1 | 定义 TensorCore 阵列规格 |

## 4. 混合扩展实现合同

| 文档 | 固定版本 | 评审范围 |
| --- | --- | --- |
| [七种顶层总览](dp/dptop/top-architectures.md) | v1.10 | 对外入口、架构差异、共用核心及兼容入口 |
| [dp/draw.io/README.md](dp/draw.io/README.md) | v1.7.8 | 六种原生可编辑架构图、嵌套关系与图例 |
| [混合顶层](dp/dptop/mixed-precision-expansion.md) | v1.9.1 | 三种现用扩展装配、输入布局、屏蔽、MAX/树、L8 与验证计划 |
| [QE lane](dp/lane/dp_lane_qe.md) | v1.9.1 | Q4E8 的紧凑解包、窄乘法和原 Q/E 流水 |
| [QE group](dp/group/dp_group_qe.md) | v1.9.1 | Q8E16 组和、无符号 scale 与兼容 S5 token |
| [Q lane](dp/lane/dp_lane_q.md) | v1.10 | Q4 专用解包、乘法、局部对齐和 S4 出口 |
| [Q group](dp/group/dp_group_q.md) | v1.10 | Q8、E8M0 scale 与兼容 S5 token |
| [Q 专用扩展顶层](dp/dptop/t8h16q64e64.md) | v1.10 | T8H16Q64E64、Q-only 参与屏蔽与九源后端 |
| [E192/E256 方案分析](dp/dptop/e192-e256-expansion-analysis.md) | v1.10（提案） | N13/N17 对齐、CSA 和 L8/L9/L10 候选，未实现 |

CModel 验证见 test/results/mixed-cmodel-v1.7.md；RTL 验证和本轮 DC 使用各自的新快照与回执。

## 5. v1.7.2 优化方案修订

按现有 N12 综合面积分解补充 [混合顶层优化约束](dp/dptop/mixed-precision-expansion.md)，将 QE 固定字段解包、分类/符号寄存压缩、E 符号压缩及扩展源整数选择裁剪分别放入所属模块文档。明确扩展仍支持 NVFP4/HiF4，原四组保留 INT8；记录 55%–65% 为目标，不是已实现收益。S3 pair 前移和小系数乘法作为待验证候选，现有流水和数值合同不变。修正 E lane 残留的复位极性说明为同步低有效 rst_n。

v1.7.2 为优化方案修订；当前 v1.7.3 已实现独立优化顶层、固定字段 QE 解包和 S1 配对摘要，并静态裁减扩展源整数选择。保持原顶层默认实现、全部 Q/E 子型及 L8/II=1，S3 pair 前移和小系数乘法仍未实施。CModel 复用位精确算法并增加 profile 别名；新旧 unpack 319488 次对照、两顶层完整回归通过，见 [功能验收](../../test/results/qe-area-opt-v1.7.3.md)。独立 N12 TT/1GHz 综合与 hold 修复已通过，见 [最终比较](../../hw/dc_syn/records/README.md#历史记录)。面积 28191.89 µm²，相对原基础 DP 增长 66.53%，用户已接受本轮约 66% 增幅；不再为原 55%–65% 区间追加 RTL 修改。

## v1.7.4 四组低精度装配

增加 [E64/Q32E64 独立顶层](dp/dptop/low-precision-tops.md)，复用 E/QE group 和五源后端；容量、合法模式由静态配置限定，数值与 L8 合同不变。验证与综合独立记录，不继承旧快照验收。

新增四组低精度验证见 [v1.7.4](../../test/results/lowp-tops-v1.7.4.md)，模型 `2db339d`、RTL `4045e00`。

两顶层均通过N12 TT/1GHz、门控开启的综合，E64/Q32E64面积为5644.14/11542.08 µm²，见 [测量记录](../../hw/dc_syn/records/README.md#历史记录)。

## v1.7.6 顶层目录与架构范围

按用户澄清保留六种架构：dp_top、E96扩展、E128扩展、优化Q64E128扩展、E64、Q32E64；加上dp_top_e兼容入口，top根目录恰好七个Verilog文件。恢复E128顶层、配置和导出/测试入口；未优化Q64E128仍退役。四个复用模块移到top/common/，模块名、算术和流水不变。详见 [六种架构对比](dp/dptop/top-architectures.md)。前次将E128移除的目录决定由本修订纠正，原测量证据不改写。

## v1.7.7 综合记录归并

按用户要求仅保留六种架构各自最新通过的综合结果，删除旧重复运行及摘要，将必要修复来源收进对应最终run的provenance/。当前面积、时序和后续功耗输入统一见 [六架构综合汇总](../../hw/dc_syn/records/latest_six_dp.md)。原始冻结RTL及验证回执保留，当前源码差异单独列明；本次不修改数值/流水合同，不新增综合或功耗测量。
