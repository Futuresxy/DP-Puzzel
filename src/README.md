# DP / Cube 设计与实现

当前架构 **v1.4**，文档整理版 **v1.4.1**。DP CModel已搭建并完成首批精度、周期与协议检查；Chisel、独立手写Verilog和Cube阵列尚未实现。

| 入口 | 内容 |
| --- | --- |
| [spec/](spec/README.md) | 三实现共同的架构、接口、数值和验证规范 |
| [cmodel/](cmodel/README.md) | C++整数位精确与逐级周期模型 |
| [chisel/](chisel/README.md) | 后续Chisel实现 |
| [verilog/](verilog/README.md) | 后续独立手写可综合RTL |
| [test/](../test/README.md) | 共用packed数据、独立参考、协议检查和报告 |

开发顺序为spec → CModel → 两套RTL → 共用RTL回归 → DC/功耗。生成RTL集中在hw/rtl/；旧hw/legacy/仅作参考，不继承其数值、周期或验证状态。

文档正文只保留当前有效定义。相邻两个主要版本的核心变更保留简短删除线，其余历史通过Git查询；见[维护规则](spec/document-control.md)。
