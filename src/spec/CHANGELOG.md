> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.4.3；修改时间：2026-11-05 00:25:00 +08:00；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 版本记录与当前索引

## 1. 主要架构版本

| 版本 | 时间（+08:00） | 核心内容 |
| --- | --- | --- |
| v1.3 | 2026-11-04 21:03:38 | S5 scale 后 LZD 仅计数；S6 按 z−d 一次双向移位；L8 默认、L9 备用。基线提交：[1f5220b](https://github.com/Futuresxy/DP-Puzzel/commit/1f5220b) |
| v1.4 | 2026-11-04 21:42:55 | NV/HiF 统一 15×9 scale 乘法；冻结首版特殊值；实现 CModel 与共用测试。 |

v1.4.1 为文档整理版：清除过时草案、旧流水图和重复索引，统一标题、表格、接口与公式排版；不改变算术、接口或默认八级边界。

v1.4.2 新增单 DP 手写 Verilog 主实现及 SystemVerilog 对照、标准 Verilog TB、Verilator 回归与源快照；冻结同步高有效复位，数值和 L8 合同不变。对应 [实现合同](dp/verilog.md)。

v1.4.3 接入新版单 DP 验证门禁与 N12 DC；Verilog 将运行时 `$clog2(elements(t))` 改为等价常量选择以兼容 DC。算术和 L8/II1 合同不变，原始基线展开失败记录与后续实测分别保留。

仅在[scale](dp/scale.md)及[特殊值](dp/special-values.md)保留 v1.3→v1.4 核心变更的删除线。更早版本由 Git 保存，非核心小修不在正文逐条累积。规则见[文档控制](document-control.md)。

## 2. 验证与实施状态

CModel 的 10747 笔精度检查、九项定向/协议测试及 sanitizer 检查通过。详见[验证报告](../../test/results/cmodel-v1.4.md)。手写两版单 DP RTL 的验证范围见 [RTL 报告](../../test/results/verilog-v1.4.md)。Chisel、阵列尚未实施；N12 TT DC 的 1.41GHz setup 未通过，见 [时序分析](../../hw/dc_syn/records/dp_n12_timing_20261105.md)。仿真通过不构成频率验收。

## 3. 当前文件索引

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [00-system-scope.md](00-system-scope.md) | v1.4.1 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.4.2 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.4.2 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.4.2 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.4.2 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.4.1 | 定义三实现共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.4.1 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.4.3 | 维护整体架构与文档版本时间线 |
| [README.md](README.md) | v1.4.2 | 汇总新版规格入口和生效范围 |
| [TEMPLATE.md](TEMPLATE.md) | v1.4.1 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.4.1 | 定义规格版本和历史修订规则 |
| [dp/README.md](dp/README.md) | v1.4.2 | 汇总 DP 主方案与设计入口 |
| [dp/cmodel.md](dp/cmodel.md) | v1.4.1 | 定义 DP CModel、模块映射及共用测试接口 |
| [dp/control.md](dp/control.md) | v1.4.2 | 定义 DP 逐请求控制与有效位推进 |
| [dp/group-normalization-options.md](dp/group-normalization-options.md) | v1.4.2 | 定义 scale 后实际指数检测与合并对齐 |
| [dp/independent-align.md](dp/independent-align.md) | v1.4.1 | 记录独立移位对齐对比方案 |
| [dp/interface.md](dp/interface.md) | v1.4.2 | 定义 DP 顶层和模块接口 |
| [dp/layout-and-scales.md](dp/layout-and-scales.md) | v1.4.2 | 定义 DP 容量与输入布局 |
| [dp/module-hierarchy.md](dp/module-hierarchy.md) | v1.4.2 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/multiplier-sharing.md](dp/multiplier-sharing.md) | v1.4.2 | 定义尾数乘法器共享和模式路由 |
| [dp/numeric-layout.md](dp/numeric-layout.md) | v1.4.2 | 推导逐级位宽和统一对齐坐标 |
| [dp/pipeline.md](dp/pipeline.md) | v1.4.2 | 定义分组共享 DP 的流水候选 |
| [dp/resource-accounting.md](dp/resource-accounting.md) | v1.4.2 | 定义可统计的功能模块边界 |
| [dp/scale.md](dp/scale.md) | v1.4.2 | 定义 scale 统一解包和 bias 处理 |
| [dp/shared-align.md](dp/shared-align.md) | v1.4.2 | 定义分组共享对齐微架构 |
| [dp/shifter-sharing.md](dp/shifter-sharing.md) | v1.4.2 | 定义固定物理移位器的 mux 复用 |
| [dp/special-values.md](dp/special-values.md) | v1.4.2 | 定义浮点分类与特殊值传播 |
| [dp/stage-formats.md](dp/stage-formats.md) | v1.4.2 | 列出每级数值出口的定点格式与指数范围 |
| [dp/unpack.md](dp/unpack.md) | v1.4.2 | 定义固定 E/M/S 解包数值布局 |
| [dp-group/README.md](dp-group/README.md) | v1.4.1 | 定义广播计算组规格 |
| [tensorcore/README.md](tensorcore/README.md) | v1.4.1 | 定义 TensorCore 阵列规格 |
| [dp/verilog.md](dp/verilog.md) | v1.4.3 | 定义单 DP 手写 RTL 实现映射及验证合同 |
