# 新版 DP / Cube 设计

当前阶段：**逐步完成整体架构 spec，尚未开始实现**。已记录 TensorCore 16×4、四个竖直 4×4 广播 DP-Group、多精度 DP、FP16 基准 K4/K8/K16、≤8 级流水、1.41 GHz 以及功耗优先的首批要求。

```text
src/
├── spec/       唯一设计合同：TensorCore、DP-Group、DP 及共用语义
├── cmodel/     spec 确认后编写的位精确、周期模型
├── chisel/     CModel 验证后开发的 Chisel 实现
└── verilog/    同一合同下独立维护的手写可综合 RTL
test/          三套代码共用的测试环境（仓库根目录）
```

开发顺序：整体 spec 定义完成并经用户确认 → CModel → Chisel / 手写 Verilog → 共用测试验证 → DC / 功耗分析。Cube 属于整体规格讨论范围，其代码同样等待规格确认。

从 [spec 索引](spec/README.md) 开始逐项讨论。未决定内容保持“待定义”，不从旧设计复制默认参数。旧 Chisel 已归档至 [hw/legacy](../hw/legacy/README.md)，只用于参考；旧验证状态不适用于新设计。

生成 RTL 继续集中于 `hw/rtl/`，测试源代码和数据在根目录 [test/](../test/README.md)，不将生成 RTL 放入测试目录。构建工具和自动化入口在实际实施时确定，本次不提供虚假的可运行实现。

~~当前全部新版 spec 已建立 **v1.0 文档基线**；后续按 [版本与修订规则](spec/document-control.md) 更新页首元信息、删除线对照及各自时间线。架构和文档版本见 [总时间线](spec/CHANGELOG.md)，新增规格使用 [模板](spec/TEMPLATE.md)。版本不改变现有“已确认/候选/待定义”状态。~~

**当前 v1.1：** 共享八级流水、模块层级、符号/幅值接口及参数推导见 [规格索引](spec/README.md)；v1.0 基线和所有修改保留于 [总时间线](spec/CHANGELOG.md)。仍按完整 spec 审查后再开展 CModel。
