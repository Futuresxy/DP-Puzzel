> 功能：定义 DP 顶层规格目录与后端边界；范围：请求/分发、C、S6 全局对齐、S7 规约、S8 输出和 E64 接入；版本：v1.7.4；修改时间：2026-11-08 09:03:06 +0800；对应代码：[dp_top.v](../../../verilog/top/dp_top.v)、[dp_global_align.v](../../../verilog/top/dp_global_align.v)、[dp_fp32_round.v](../../../verilog/arithmetic/dp_fp32_round.v)、[共用 CModel 后端](../../../cmodel/lib/top/backend.cpp)、[dp_top_e.v](../../../verilog/top/dp_top_e.v)；Chisel 尚未实现。

# dptop：接口、全局对齐与输出

顶层实例化 G=K_FP16/4 个基本组，默认 G=4；单笔输出 scaled_dot(A,B)+C。G 组及一份 C 对应 G+1 个最终规约源。顶层没有跨请求累加状态，输入为 A/B/C 原子接收，输出无背压。

## 1. 接口和整体组织

| 主题 | 规格 |
| --- | --- |
| 完整端口、datatype、内部 token | [interface.md](interface.md) |
| A/B 位切片、scale 广播、HiF4 元数据 | [layout-and-scales.md](layout-and-scales.md) |
| 各层所有权、S6 新源接入与观察时刻 | [module-hierarchy.md](module-hierarchy.md) |
| 逐请求模式、valid/bubble、last、复位 | [control.md](control.md) |
| S1–S8 及 L9 静态探索边界 | [pipeline.md](pipeline.md) |

## 2. 顶层计算模块

| 阶段 | 计算单元 | 默认数值出口 | 详细规格 |
| --- | --- | --- | --- |
| S1–S4 | 一份 C raw32 与类型传递 | 原始编码，不重复保存解包记录 | [interface.md](interface.md) |
| S5 | FP32/INT32 C 解包及 LZD | 独立符号+M32、anchor、z、特殊值 | [逐级格式](../common/stage-formats.md) |
| S6 | G 组+C 的实际指数 MAX、一次双向幅值移位、符号恢复 | 五路 40 位 TC，浮点 F38 | [global-align.md](global-align.md) |
| S7 | G+1 路完整增长的平衡规约树 | 43 位 TC，浮点 S1I4F38 | [数值推导](../common/numeric-layout.md) |
| S8 | 总和符号分离、LZD/norm/RNE、特殊结果选择 | FP32 或 INT32 回绕 | [特殊值/舍入](../common/special-values.md) |

GLOBAL_W 独立控制 S6 含符号窗口，默认 40；幅值网络宽 GLOBAL_W−1。源 token 的 A_raw 已吸收各自 F，S6 按 e=A_raw−z 比较、按 net=A_raw−E_max 移位，不再次按 datatype 扣除 F。主实现的整数结构落位、特殊值及完整增长位继续按共用合同执行。

## 3. E64 专用前端接入

[E8 lane](../lane/dp_lane_E.md) 和 [E16 group](../group/dp_group_E.md) 提出 4×E16 的 E64 前端。用户已明确兼容 group 输出字段、默认 M31 和 S5 到达拍，因此 S5 C 解包及 S6–S8 的算法、补零和寄存位置可复用。

E-only 接入口限制合法格式为 MXFP4/NVFP4/HiF4、C/D 为 FP32；HiF4 新坐标由 group 生成正确的 magnitude/A_raw/z。该前端通过 CModel 的静态 frontend 配置及 RTL 顶层 dp_top_e 接入。CModel 共用后端函数；RTL 共用 C 解包、全局对齐、平衡树及 FP32 舍入模块定义，流水寄存器由各自 top 持有。E 顶层删除整数落位、类型寄存和 INT32 输出选择。后端复用不构成新的频率/PPA 通过证据。

## 4. 候选与验证入口

[独立整体对齐](independent-align.md) 为后续另一架构候选，不能混入当前主实现。[实现映射](../implementation/verilog.md)、[CModel](../implementation/cmodel.md) 和 [资源统计](../implementation/resource-accounting.md) 统一追踪各层源码、快照、验证和 PPA 来源。架构图仍保留在 [draw.io](../draw.io/dp_arch.drawio)。

## 5. 混合低精度扩展

[混合顶层合同](mixed-precision-expansion.md) 定义 dp_top_t8h16q32e96、dp_top_t8h16q32e128、dp_top_t8h16q64e128。基础四组和新增 E/QE 分支共用 S5 token；S6 先合并带参与资格的指数 MAX，再逐源对齐；S7 分支求和，高精度旁路扩展合并，S8 只做一次最终编码。N=7/9 时默认总和宽为 43/44，保持 L8/II=1。源参与、有限非零、特殊值与负零分别处理，避免闲置 token 污染结果。

三个固定配比顶层与原多精度/E 顶层独立导出和验证；原接口表描述原顶层，新增物理组宽度见混合顶层合同。

## 6. 四组低精度独立顶层

[低精度顶层](low-precision-tops.md) 定义 dp_top_e64 与 dp_top_q32e64，共用五源后端，分别使用四个 E/QE group，保持 L8/II=1。
