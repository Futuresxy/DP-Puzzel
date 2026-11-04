> 功能：汇总 DP 主方案与设计入口；范围：分组共享 DP、外部边界和后续独立对齐探索；版本：v1.4.1；修改时间：2026-11-04 22:08:44 +08:00；对应代码：[CModel include/dp/model.hpp](../../cmodel/include/dp/model.hpp)；Chisel/手写 Verilog 模块尚未实现。

# 多精度 DP 设计

当前实现分组共享计算方案。每笔完成 `scaled_dot(A,B)+C`，没有跨请求累加状态。默认容量为 **T8H16Q32E64**，所有格式共用八级寄存边界；CModel 已完成首批测试。

## 1. 层级与术语

| 层级 | 容量 | 主要功能 |
| --- | --- | --- |
| lane | T1H2Q4E8 | 解包、元素乘法、局部对齐与规约 |
| 基本组 | T2H4Q8E16 | 两条 lane 共享指数基准、组和与 scale |
| DP | G 个基本组；G=K_FP16/4 | 所有组与 C 对齐、累加、输出 |

T=TF32，H=FP16/BF16，Q=MXFP8/6，E=MXFP4/NVFP4/HiF4。INT8 与 Q 同并行度，C/D 解释为 INT32。K4/K8/K16 分别实例化 1/2/4 个基本组。

## 2. 当前数据路径

S1 解包 A/B/scale → S2 尾数乘法与指数 MAX → S3 幅值 RTZ/E pair → S4 lane 树 → S5 组和/scale/abs/LZD 计数及 C 解包 → S6 一次双向对齐 → S7 总树 → S8 FP32 RNE 或 INT32 回绕。

S5 保留未左移幅值、无偏原 anchor 和 z。S6 先求真实指数 MAX，再执行净位移 z−d。NVFP4/HiF4 共用 15×9 scale 乘法器，不再添加格式缩位 mux。

## 3. 规范导航

| 内容 | 入口 |
| --- | --- |
| 层级与流水 | [模块边界](module-hierarchy.md) · [流水](pipeline.md) · [分组共享方案](shared-align.md) |
| 数据与控制 | [接口](interface.md) · [容量/scale 布局](layout-and-scales.md) · [控制](control.md) |
| 数值 | [解包](unpack.md) · [逐级格式](stage-formats.md) · [位宽推导](numeric-layout.md) · [特殊值](special-values.md) |
| 资源 | [乘法共享](multiplier-sharing.md) · [移位共享](shifter-sharing.md) · [scale](scale.md) · [组间对齐](group-normalization-options.md) |
| 实施 | [CModel](cmodel.md) · [功能统计](resource-accounting.md) · [独立对齐候选](independent-align.md) |

## 4. 当前边界

A/B 首版同格式，合法请求可逐拍换型，last 只透传。无输出背压；输入缺失不暂停在途请求。默认 L8，备用 L9 静态配置只作探索。

独立一次对齐、专用 Q/E/QE 增源、阵列和两套 RTL 尚未实现。功耗优先、1.41GHz 以及整体精度目标仍须后续证据支持。
