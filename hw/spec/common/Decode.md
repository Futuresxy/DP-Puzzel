# Decode.scala：元素、scale 与 C 解码

对应源码：[Decode.scala](../../chisel_src/common/Decode.scala)。内联组合函数，PE 自己放置 S1 解码寄存器；C 路径在 S10 采样解码结果。没有隐藏握手或额外周期。

## 架构和理由

用一个参数化浮点解码函数覆盖 H/Q 格式，静态 `hasH/hasQ/hasE` 决定生成哪些分支。解码分离 numeric 和 special：Inf/NaN 用有限安全数值占位，分类走旁路，避免特殊编码误参与指数 MAX。Q 的两个尾数相邻打包，去掉旧 slot2/sign1 的隐含映射。

| 元素 | 解包尾数 | 解包指数/解释 |
| --- | --- | --- |
| FP16 | 12-bit UQ1.11，LSB 为补零 | 5-bit effective exponent，bias 15 |
| BF16 | 8-bit UQ1.7 | 8-bit effective exponent，bias 127 |
| FP8/FP6 | 每 lane 4-bit UQ1.3 | 每 lane 5-bit，统一 bias 15 |
| MX/NV E2M1 | 每 lane 4-bit UQ3.1 | 元素指数融入尾数，无独立指数 |
| HiF4 | 每 lane 4-bit UQ2.2 | group0 已融入尾数，指数为 group1 0/1 |

H/Q subnormal 使用有效指数 1、隐藏位 0，保留非正规数。FP16、BF16、E5M2 有 Inf/NaN；E4M3 仅 exp/frac 全 1 是 NaN，其他最高指数码有限；FP6 全部码有限。FP6 占一个 8-bit 槽，低 6 位有效，高 2 位忽略；并非紧凑的 6-bit 传输格式。

E2M1 的整数尾数为 `[0,1,2,3,4,6,8,12]`，除 2 得到绝对值。HiF4 暂按源工程合同：3-bit magnitude 除 4，再乘 `2^group0` 和 `2^group1`；主 scale 为 `2^(exp6−48) × (1+frac2/4)`，exp=0 仍有隐藏 1，0xff 为 NaN。这是迁移的实验性编码，外部论文/规范版本仍待确认。

## scale 与边界

解码 scale 为 `{exponent:S9, mantissa:U4, nan, zero}`，数值 `mantissa/8 × 2^exponent`。E8M0 exponent=raw−127、mantissa=8，0xff 为 NaN（0x00 不是零）；NV 使用非负 E4M3，允许零/subnormal，输入 bit7 必须为 0；HiF4 为上述 E6M2。H 固定 1.0，输入 scale/group bits 忽略。

四字一组，组编号 g 的 scale 槽：Q 和 HiF4 为 0，MXFP4 为 floor(g/2)，NVFP4 为 g。Q32 对应一个 32 元素块；E64 对应两个 MX32 或四个 NV16；E32 对应一个 MX32 或两个 NV16。HiF4 E32 是一个 64 元素块的一半，上游必须复制主 scale 并切分 group bits，不能重新定义量化块。

NVFP4 张量级 FP32 scale 不属于此 block 接口，需在未来算子级合同中单独处理；当前不声称完成某厂商全部量化/反量化流水。

先组合 element/scale 分类，再形成乘积分类：NaN 优先、0×Inf 为 NaN、Inf 符号异或。scale=0 的 NV 数值在后续 scale 乘法归零。最终各组规约 special，避免逐 lane 分类在全流水中传递。

C 解码支持 FP32/FP16/BF16，统一为 W24 magnitude + sign、物理 top exponent，FP16/BF16 只附加低零，不舍入；Inf/NaN 数值部分清零。C 的 LZD 规格化由 Accumulate 在 S11 完成。

## 验收与来源

待 SV 验收：全部小格式编码、subnormal、E4M3 最大有限值、MX NaN scale、NV 零/最大 scale、HiF4 局部缩放、混合 Q 和 MX/NV 的独立 scale。

MX 编码及 32 元素块参考 [OCP MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)。NV 的双层缩放背景参考 [NVIDIA Transformer Engine NVFP4 文档](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/nvfp4/nvfp4.html)。迁移合同仍以本 spec 和后续 RTL 验收为准，不能由外部格式说明推断本硬件已通过验证。
