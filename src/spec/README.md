# 多精度 TensorCore 规格

状态：**第一批架构要求已确认，详细合同继续完善；尚未进入实现**。本轮依据为用户 2026-11-04 的需求，不沿用旧 PE 的结构、数值和周期合同。

## 三层设计入口

| 层级 | 文档 | 已确认要求 |
| --- | --- | --- |
| TensorCore | [阵列组织](tensorcore/README.md) | 16×4 个 DP；四个 DP-Group 沿竖直方向拼接 |
| DP-Group | [广播计算组](dp-group/README.md) | 每组 4×4 个 DP，组内广播，DP 间无脉动 |
| DP | [多精度点积](dp/README.md) | FP16 K4 基本组 T2H4Q8E16；并行组合成 K8/K16；分组共享是当前主方案 |

支持 TF32（每元素输入容器 32 位）、FP16、BF16、MXFP8、MXFP6、MXFP4、NVFP4、HiF4 和 INT8；暂不支持 HiF8。INT8 的计算并行度与 MXFP8 相同，可旁路浮点专用级；保留整数乘法/累加/加 C，精确延迟由省去浮点对齐/归一化/舍入后的流水切分决定。

精度要求为：TF32/FP16/BF16/MXFP8/MXFP6 至少保留 25 位；MXFP4/NVFP4 保留 35 位；HiF4 复用 NVFP4 通路，以约 37 位作为待推导目标。保留宽度的计数口径和所在节点仍待确认，见 [数值语义](01-numerics.md)。

目标频率 **1.41 GHz**。精度、支持模式、时序和延迟约束满足后，**功耗优先，面积其次**。所有设计量集中命名、参数化或按公式派生，禁止散落魔鬼数值。

## 共用合同

| 文档 | 内容 |
| --- | --- |
| [系统范围](00-system-scope.md) | 目标、边界及要求状态 |
| [数值语义](01-numerics.md) | 格式、保留精度、特殊值、数学参考与 NVIDIA 证据边界 |
| [DP 固定解包](dp/unpack.md) | E/M/S 布局、原子块与 lane、I1F10/I1F7/I1F3/I3F1/I2F2 |
| [DP 特殊值](dp/special-values.md) | IEEE 分类、乘加例外、分组/scale/C 传播和待决数值规则 |
| [接口与协议](03-interfaces.md) | TF32 容器、数据与 scale、事务和输出边界 |
| [周期与状态](04-timing-state.md) | ≤8 级、INT8 旁路、时钟和状态推进 |
| [参数与配置](06-configuration.md) | 集中参数、派生关系、合法性与未决倍率 |
| [验证合同](07-verification.md) | 三实现一致性、精度、结构、周期及配置矩阵 |
| [实现与 PPA](08-implementation-ppa.md) | 功耗优先设计、时序约束和证据要求 |

“已确认要求”来自用户；“派生关系”来自这些要求的算术推导；“建议”与“待确认”不构成已批准微架构。完整 spec 闭合并确认后，按 CModel → Chisel / 手写 Verilog → 共用验证 → EDA 推进。未决项统一见 [roadmap](../../docs/roadmap.md)。
