> 功能：定义数值语义与保留精度；范围：全部数值模式、缩放、精度窗口和 FP32 输出；版本：v1.5；修改时间：2026-11-05 11:30:00 +08:00；对应代码：[CModel lib/arithmetic.cpp](../cmodel/lib/arithmetic.cpp)；分组主方案手写 RTL：[dp_top.v](../verilog/top/dp_top.v)；Chisel 尚未实现。

# 数值语义与保留精度

## 1. 格式与计算边界

| 族 | 输入与内部幅值 | scale | 输出 |
| --- | --- | --- | --- |
| T：TF32 | 32 位容器，高 19 位有效；I1F10 | 无 | FP32 |
| H：FP16 / BF16 | I1F10 / I1F7 | 无 | FP32 |
| Q：MXFP8 / MXFP6 | 四种子型统一重编码为 E5M3 / I1F3 | E8M0 | FP32 |
| E：MXFP4 / NVFP4 | E2M1 精确转 I3F1 | E8M0 / 非负 E4M3 | FP32 |
| E：HiF4 | S1P2，e1 融入 I2F2，e2 保留为指数 | E6M2，bias=48 | FP32 |
| INT8 | 有符号 8 位，安全解为 sign+幅值 | 无 | INT32 |

A/B 首版仅同格式；混合格式相乘未启用。HiF8 不支持。每笔浮点运算为缩放点积加 FP32 C；整数为精确 signed INT8 点积加 INT32 C 后模 2^32 回绕。scale 不作用于 C，DP 不处理跨请求依赖。

## 2. 保留精度与截断点

T/H/Q 在 S3 使用 S0I2F(LOCAL_W-2)，默认 28 位幅值窗口为 S0I2F26；右移 RTZ 后恢复符号，进入自然增长的补码树。E 通过两位保护低零支持 HiF4 的 0/1/2 位局部对齐，该处保持精确。INT8 的低零仅为结构落位，不能引入精度损失。

S5 分离组和的符号与幅值。NVFP4/HiF4 的公共 14×8 无符号 scale 乘法保留完整 22 位幅值积。scale 后 LZD 仅计数，S6 按真实指数选 MAX 并做一次双向移位；默认全局窗口 40 位含符号，即 39 位幅值。右移 RTZ，S7 保留完整求和，S8 对实际有限位宽总和作 RNE。

局部 25 位的小数口径已经落实；FP4 的 35 位和 HiF4 约 37 位是整体精度目标，仍需结合对齐点、强抵消和误差指标验收。总线宽度、结构补零和有效数学精度不能直接等同。各级 F、整数位和 anchor 见[出口表](dp/stage-formats.md)。

## 3. 特殊值与最终编码

S1 分类 A/B/scale，S5 分类 C。NaN、Inf、0×Inf、异号 Inf 相加及 sNaN 按[特殊值合同](dp/special-values.md)传播；S8 选择特殊结果或有限数编码。

首版仅 RNE，canonical qNaN=0x7fc00000，渐进下溢，tininess 在舍入后判断。精确抵消为+0，全为负零时保留−0；异常仅记验证 trace。两次 RTZ 丢位单独记录，不重新注入 S8 的 sticky。

## 4. 数学参考与实现一致性

CModel 按固定窗口建模；独立 Fraction 参考分别计算相同 RTZ 网格和精确数学点积。RTL 须逐位匹配 CModel，数学误差另行报告。TF32 另用 FP64 近似并复核舍入边界；INT8 必须精确一致。见[验证合同](07-verification.md)。

## 5. 外部依据的边界

NVIDIA CUDA 13.0.2 归档 PTX ISA 9.0 规定 TF32 使用 32 位容器，并描述相应 MMA 的中间累加语义；它并未完整规定本项目的分组次序及 25/35/37 位物理窗口。参见[类型定义](https://docs.nvidia.com/cuda/archive/13.0.2/parallel-thread-execution/index.html#alternate-floating-point-data-formats)与[MMA 数值语义](https://docs.nvidia.com/cuda/archive/13.0.2/parallel-thread-execution/index.html#warp-level-matrix-instructions-mma)。

这些位宽是用户给定的项目要求/目标，不作为 NVIDIA 官方保证或本项目已完成的逆向测量。HiF4 采用用户明确指定的字段及 scale 定义，来源见[解包规范](dp/unpack.md)。
