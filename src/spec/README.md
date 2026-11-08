> 功能：汇总新版规格入口和生效范围；范围：TensorCore、DP-Group、DP 及共用合同；版本：v1.7.5；修改时间：2026-11-08 09:15:35 +0800；对应代码：[CModel include/dp/model.hpp](../cmodel/include/dp/model.hpp)；分组主方案手写 RTL：[dp_top.v](../verilog/top/dp_top.v)；Chisel 尚未实现。

# 多精度 DP / Cube 设计规范

本规范定义一套由 CModel、Chisel 与独立手写 Verilog 共同遵循的硬件合同。**当前架构为 v1.7，实现映射为 v1.7.5；当前维护 DP CModel 与手写 Verilog；SystemVerilog 冻结为 T8H16Q32E64 历史参考，Chisel 与阵列尚未实现。**

## 1. 阅读路径

| 阅读目的 | 文档 |
| --- | --- |
| 理解目标、边界与层级 | [系统范围](00-system-scope.md) · [TensorCore](tensorcore/README.md) · [DP-Group](dp-group/README.md) |
| 五种现用顶层及其区别 | [顶层架构总览](dp/dptop/top-architectures.md) |
| 理解当前 DP 架构 | [DP 导读](dp/README.md) · [模块层级](dp/dptop/module-hierarchy.md) · [八级流水](dp/dptop/pipeline.md) |
| 按计算模块阅读 | [lane](dp/lane/README.md) · [group](dp/group/README.md) · [dptop](dp/dptop/README.md) |
| 对接数据与控制 | [顶层接口](dp/dptop/interface.md) · [输入布局](dp/dptop/layout-and-scales.md) · [逐请求控制](dp/dptop/control.md) |
| 核对计算与位宽 | [解包](dp/lane/unpack.md) · [逐级定点格式](dp/common/stage-formats.md) · [数值推导](dp/common/numeric-layout.md) |
| 理解共享资源 | [乘法器](dp/lane/multiplier-sharing.md) · [移位器](dp/lane/shifter-sharing.md) · [scale](dp/group/scale.md) · [组间对齐](dp/dptop/global-align.md) |
| 运行与评估模型 | [CModel 合同](dp/implementation/cmodel.md) · [构建入口](../cmodel/README.md) · [测试报告](../../test/results/cmodel-v1.4.md) |
| 手写 RTL | [实现合同](dp/implementation/verilog.md) · [源码](../verilog/README.md) · [验证报告](../../test/results/verilog-v1.4.md) |
| 讨论 E 类专用 DP | [E8 lane](dp/lane/dp_lane_E.md) · [E16 group 与 FP32 后端接入](dp/group/dp_group_E.md)（e2 定点融合、兼容 group 输出；E CModel / RTL 已实现并验证） |
| 评审低精度算力扩展 | [混合 E96/优化 Q64E128 顶层](dp/dptop/mixed-precision-expansion.md) · [QE lane](dp/lane/dp_lane_qe.md) · [QE group](dp/group/dp_group_qe.md)（v1.7.4，CModel/RTL已实现） |
| 低精度独立 DP | [四组 E64 / Q32E64](dp/dptop/low-precision-tops.md)，仅低精度前端，五源浮点后端 |
| 准备 PPA | [参数](06-configuration.md) · [验证](07-verification.md) · [实现与 PPA](08-implementation-ppa.md) · [功能块统计](dp/implementation/resource-accounting.md) |

## 2. 设计摘要

| 项目 | 当前定义 |
| --- | --- |
| 阵列 | TensorCore 为 16×4 DP；四个 4×4 广播 DP-Group 竖直拼接；组内无脉动 |
| DP 组织 | T1H2Q4E8 → T2H4Q8E16 → T8H16Q32E64 |
| 配置 | FP16 基准 K∈{4,8,16}，基本组数 G=K/4；局部/全局窗口默认 28/40 |
| 数值格式 | TF32、FP16、BF16、MXFP8/6/4、NVFP4、HiF4、INT8；不支持 HiF8 |
| 运算边界 | 一笔请求完成 scaled_dot(A,B)+C；浮点输出 FP32，整数输出 INT32 |
| 流水 | 默认 L8、II=1；L9 仅为静态备用探索；无输出背压 |
| 资源选择 | S5 分离符号与幅值，NVFP4/HiF4 共用 14×8 无符号 scale 乘法；S5 LZD 仅计数，S6 一次双向移位 |
| 目标 | 1.41 GHz；满足精度与吞吐后，功耗优先、面积其次 |

验证与 PPA 结论需按实现快照分别引用；默认 LOCAL_W=28，对 Q 乘积局部窗口 P=26，其他模式依逐级 S/I/F 表解释；FP4 35 位 / HiF4 约 37 位目标的整体误差判据仍需继续评估。

混合组扩展保持 T/H 容量，分别扩 E 到 K96/K128、Q 到 K64。物理源数为7/9，参与掩码逐请求保存，S7 宽度按物理源数自然增长；具体接口见混合顶层合同。

## 3. 文档约定

正文只呈现当前有效合同和明确标注的候选。仅相邻两个主要架构版本的**核心变更**保留删除线对照，非核心小修直接更新；完整历史由 Git 保存。见 [文档控制](document-control.md) 与 [版本记录](CHANGELOG.md)。
