> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.5.9；修改时间：2026-11-06 09:36:04 +08:00；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 版本记录与当前索引

## 1. 主要架构版本

| 版本 | 时间（+08:00） | 核心内容 |
| --- | --- | --- |
| v1.4 | 2026-11-04 21:42:55 | NV/HiF 统一 15×9 scale 乘法；冻结首版特殊值；实现 CModel 与共用测试。 |
| v1.5 | 2026-11-05 11:30:00 | NVFP4/HiF4 的 S5 scale 改为分离符号和幅值后使用 14×8 无符号乘法，乘积保持 22 位。 |

v1.4.1 为文档整理版：清除过时草案、旧流水图和重复索引，统一标题、表格、接口与公式排版；不改变算术、接口或默认八级边界。

v1.4.2 新增单 DP 手写 Verilog 主实现及 SystemVerilog 对照、标准 Verilog TB、Verilator 回归与源快照；冻结同步高有效复位，数值和 L8 合同不变。对应 [实现合同](dp/implementation/verilog.md)。

v1.4.3 接入新版单 DP 验证门禁与 N12 DC；Verilog 将运行时 `$clog2(elements(t))` 改为等价常量选择以兼容 DC。算术和 L8/II1 合同不变，原始基线展开失败记录与后续实测分别保留。

v1.4.4 将 S3 默认幅值窗口调整为 28 位，S6 继续使用 40 位含符号窗口。逐级 SxIxFx、树宽与静态补零均由 K 和两个窗口推导；增加 Verilator 窗口扫参入口。

v1.5.1 将 S5 无符号 scale 落地到 CModel、Verilog 和 SystemVerilog，更新 S5 乘法 trace 与边界验证。

[scale](dp/group/scale.md) 保留 v1.4 → v1.5 的核心变更对照。更早版本由 Git 保存，非核心小修不在正文逐条累积。规则见[文档控制](document-control.md)。

v1.5.8 在已有 E CModel 上实现 dp_lane_e/dp_group_e/dp_top_e，保留 10/12/15 位窄规约与 S5 兼容 token，复用后端算术模块；新增 files_e.f、E TB 观察适配和独立验证门禁。E64 三格式各 961 笔、5288 定向、六组参数输出及 1106924 个断点通过；原多精度完整回归保持通过。按用户授权进行 N12 TT、1GHz、28/40 的同工况 DC 面积/时序比较，并将验证及综合证据标记长期保留；结果见 [E64 回归](../../test/results/e64-v1.5.8.md) 与 [DC 对比](../../hw/dc_syn/records/e64_n12_comparison_20261105.md)。修复综合后缓存时钟 collection 过期导致 hold 命令失效的问题；无效首轮另存，不作为正式面积比较。混合组、Chisel、真实负载功耗仍待实施；SV 继续冻结。

v1.5.9 将 E lane 内联解码提取为独立组合模块 dp_lane_unpack_e，A/B 各实例化一份；S1 寄存仍由 lane 持有，数值与 L8/II1 不变。更新 E 清单/源码映射；新快照完整 Verilator 回归通过（三格式各961笔、5288定向、六组参数及1106924个断点）；多精度与冻结 SV 不变，原 DC 结果不授予新快照。

## 2. 验证与实施状态

v1.5.1 的 CModel 与两版 RTL 均通过 10747 笔固定输入和无符号 scale 定向检查。验证范围与回执见 [v1.5.1 回归报告](../../test/results/verilog-v1.4.md)。Chisel、阵列尚未实施；历史 27/40 配置的 N12 TT DC 在 1.41GHz setup 未通过，见 [时序分析](../../hw/dc_syn/records/dp_n12_timing_20261105.md)。仿真通过不构成频率验收。

## 3. 当前文件索引

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [README.md](README.md) | v1.5.8 | 汇总新版规格入口和生效范围 |
| [00-system-scope.md](00-system-scope.md) | v1.5.8 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.5.4 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.5.4 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.5.4 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.5.7 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.5.8 | 定义现用模型/RTL及未来实现的共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.5.5 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.5.9 | 维护整体架构与文档版本时间线 |
| [TEMPLATE.md](TEMPLATE.md) | v1.4.1 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.5.4 | 定义规格版本和历史修订规则 |
| [dp/README.md](dp/README.md) | v1.5.8 | 按模块与共用合同组织 DP 规格 |
| [dp/lane/README.md](dp/lane/README.md) | v1.5.8 | 定义 lane 规格目录与计算边界 |
| [dp/lane/dp_lane_E.md](dp/lane/dp_lane_E.md) | v1.5.9 | 讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合 |
| [dp/lane/multiplier-sharing.md](dp/lane/multiplier-sharing.md) | v1.5.4 | 定义尾数乘法器共享和模式路由 |
| [dp/lane/shifter-sharing.md](dp/lane/shifter-sharing.md) | v1.5.4 | 定义固定物理移位器的 mux 复用 |
| [dp/lane/unpack.md](dp/lane/unpack.md) | v1.5.4 | 定义固定 E/M/S 解包数值布局 |
| [dp/group/README.md](dp/group/README.md) | v1.5.8 | 定义 group 规格目录与计算边界 |
| [dp/group/dp_group_E.md](dp/group/dp_group_E.md) | v1.5.8 | 讨论 E16 定点组规约及兼容的 group 输出 |
| [dp/group/scale.md](dp/group/scale.md) | v1.5.4 | 定义 scale 统一解包和 bias 处理 |
| [dp/group/shared-align.md](dp/group/shared-align.md) | v1.5.4 | 定义分组共享对齐微架构 |
| [dp/dptop/README.md](dp/dptop/README.md) | v1.5.8 | 定义 DP 顶层规格目录与后端边界 |
| [dp/dptop/control.md](dp/dptop/control.md) | v1.5.4 | 定义 DP 逐请求控制与有效位推进 |
| [dp/dptop/global-align.md](dp/dptop/global-align.md) | v1.5.4 | 定义 scale 后实际指数检测与合并对齐 |
| [dp/dptop/independent-align.md](dp/dptop/independent-align.md) | v1.5.4 | 记录独立移位对齐对比方案 |
| [dp/dptop/interface.md](dp/dptop/interface.md) | v1.5.4 | 定义 DP 顶层和模块接口 |
| [dp/dptop/layout-and-scales.md](dp/dptop/layout-and-scales.md) | v1.5.4 | 定义 DP 容量与输入布局 |
| [dp/dptop/module-hierarchy.md](dp/dptop/module-hierarchy.md) | v1.5.8 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/dptop/pipeline.md](dp/dptop/pipeline.md) | v1.5.4 | 定义分组共享 DP 的流水候选 |
| [dp/common/numeric-layout.md](dp/common/numeric-layout.md) | v1.5.4 | 推导逐级位宽和统一对齐坐标 |
| [dp/common/special-values.md](dp/common/special-values.md) | v1.5.4 | 定义浮点分类与特殊值传播 |
| [dp/common/stage-formats.md](dp/common/stage-formats.md) | v1.5.4 | 列出每级数值出口的定点格式与指数范围 |
| [dp/implementation/cmodel.md](dp/implementation/cmodel.md) | v1.5.8 | 定义 DP CModel、模块映射及共用测试接口 |
| [dp/implementation/resource-accounting.md](dp/implementation/resource-accounting.md) | v1.5.5 | 定义可统计的功能模块边界 |
| [dp/implementation/verilog.md](dp/implementation/verilog.md) | v1.5.9 | 定义手写 RTL 实现映射及验证合同 |
| [dp-group/README.md](dp-group/README.md) | v1.4.1 | 定义广播计算组规格 |
| [tensorcore/README.md](tensorcore/README.md) | v1.4.1 | 定义 TensorCore 阵列规格 |
