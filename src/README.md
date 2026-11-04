# DP / Cube 设计与实现

当前架构 **v1.4**，实现映射 **v1.4.2**。DP CModel、独立手写 Verilog 与 SystemVerilog 对照已建立；两版 RTL 共用 Verilog TB 验证。Chisel 和 Cube 阵列尚未实现。

| 入口 | 内容 |
| --- | --- |
| [spec/](spec/README.md) | 三实现共同的架构、接口、数值和验证规范 |
| [cmodel/](cmodel/README.md) | C++整数位精确与逐级周期模型 |
| [chisel/](chisel/README.md) | 后续Chisel实现 |
| [verilog/](verilog/README.md) | 单 DP Verilog 主实现与 SystemVerilog 对照 |
| [test/](../test/README.md) | 共用packed数据、独立参考、协议检查和报告 |

开发顺序为spec → CModel → 两套RTL → 共用RTL回归 → DC/功耗。生成RTL集中在hw/rtl/；旧hw/legacy/仅作参考，不继承其数值、周期或验证状态。

文档正文只保留当前有效定义。相邻两个主要版本的核心变更保留简短删除线，其余历史通过Git查询；见[维护规则](spec/document-control.md)。
