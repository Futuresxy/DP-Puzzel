> 功能：汇总共用输入输出协议；范围：A/B/C、scale、metadata、逐笔 datatype 和 valid/last；版本：v1.5.4；修改时间：2026-11-05 14:16:26 +08:00；对应代码：[CModel include/dp/model.hpp](../cmodel/include/dp/model.hpp)；分组主方案手写 RTL：[dp_top.v](../verilog/top/dp_top.v)；Chisel 尚未实现。

# 共用输入输出合同

完整信号、编码和位切片以 [DP 接口](dp/dptop/interface.md) 为准；本页汇总跨实现必须一致的边界。

## 1. 原子请求

请求包含 A、B、C、两侧 scale、HiF4 metadata、各自 datatype 及 last。只有 A/B/C 同时 valid 且类型元组合法时共同握手，无部分接收和内部拼接队列。scale/metadata 随所属操作数同拍传入。

A/B 首版仅支持同格式相乘，独立类型字段保留。浮点 C/D 为 FP32，INT8 C/D 为 INT32。C 在 S1–S4 保存 raw32，在 S5 按本笔类型解包。

## 2. 数据布局

| 数据 | 外部布局 |
| --- | --- |
| TF32 | 每元素 32 位；S[31]、E[30:23]、F[22:13]、低 13 位零 |
| FP16 / BF16 | 每元素 16 位，低元素索引在总线低位 |
| MXFP8 / INT8 | 每元素 8 位 |
| MXFP6 | 每元素 8 位；有效编码在[7:2]，低 2 位零 |
| MXFP4 / NVFP4 / HiF4 | 每元素 4 位，紧密排列 |

scale 以 E16 基本组为物理槽。Q32 共用一个 scale 并广播四份；MXFP4 E64 的两个原生 scale 各广播两份；NVFP4 每槽独立；HiF4 E64 的一个 scale 广播四份。HiF4 每槽有 4 个 e1 和 2 个 e2，均为 1 位，两侧独立。

## 3. 结果与控制

输出包括 valid、32 位 D、D datatype 和 last，无 ready。相邻请求可以切换合法格式；每级控制与数据同行，last 只透传，不触发锁定或排空。复位统一取消在途请求。

共享测试格式为 [DP_INPUTS_V1](../../test/data/README.md)。该文件已完成物理打包，后续 testbench 不重新量化或广播。
