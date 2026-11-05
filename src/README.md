# DP / Cube 设计与实现

当前架构 **v1.5**，实现映射 **v1.5.1**。当前维护 CModel 与独立手写 Verilog；SystemVerilog 冻结为 T8H16Q32E64 历史参考，后续不再同步新功能。Chisel 和 Cube 阵列尚未实现。

| 入口 | 内容 |
| --- | --- |
| [spec/](spec/README.md) | 架构、接口、数值和验证规范 |
| [cmodel/](cmodel/README.md) | C++整数位精确与逐级周期模型 |
| [chisel/](chisel/README.md) | 后续Chisel实现 |
| [verilog/](verilog/README.md) | 单 DP Verilog 主实现；SystemVerilog 历史参考 |
| [test/](../test/README.md) | 共用packed数据、独立参考、协议检查和报告 |

当前开发顺序为 spec → CModel → 手写 Verilog → 共用 RTL 回归 → DC/功耗。未来 Chisel 路径另行实施，SV 历史目录不接收新特性。用于分析的 RTL 快照集中于 `hw/rtl/`。历史实现从 Git 查阅。

文档正文只保留当前有效定义。相邻两个主要版本的核心变更保留简短删除线，其余历史通过Git查询；见[维护规则](spec/document-control.md)。
