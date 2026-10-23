# Formats.scala：格式与兼容关系

对应源码：[Formats.scala](../../chisel_src/config/Formats.scala)。纯组合生成函数，不产生独立 Module 或状态。

保留源工程的数据类型编码，降低后续向量转换成本；删除与数据格式重复的 scale-type 字段，scale 类型由格式唯一决定，杜绝 NVFP4 配 E8M0 这类矛盾配置。

| 4-bit 编码 | 格式 | 家族 | scale |
| --- | --- | --- | --- |
| 0 | NVFP4 E2M1 | E | 非负 E4M3，16 元素/块 |
| 1 | MXFP4 E2M1 | E | E8M0，32 元素/块 |
| 2 | 源工程 HiF4 | E | E6M2 主 scale + group0/group1 |
| 3 | MXFP6 E2M3 | Q | E8M0，32 元素/块 |
| 4 | MXFP6 E3M2 | Q | E8M0，32 元素/块 |
| 5 | MXFP8 E4M3 | Q | E8M0，32 元素/块 |
| 6 | MXFP8 E5M2 | Q | E8M0，32 元素/块 |
| 7 | BF16 | H | 恒等 scale，忽略 scale 输入 |
| 8 | FP16 | H | 恒等 scale，忽略 scale 输入 |

9–15 未支持，不能解释为旧工程 INT/TF32 模式。

A/B 合法组合：H 必须同格式；任意 Q 格式可互乘，分别解码到 E5 基准后共享坐标；MXFP4 与 NVFP4 可互乘；HiF4 只与 HiF4 配对。H/Q/E 跨家族互乘不支持。

`product` 只选择内部固定点坐标：Q 统一使用 E5M2 选择码（其尾数已经统一为 UQ1.3）；MX/NV 混合按 NV 坐标保留分数 scale。该选择码不是重新解释原始输入编码，不能在独立解码之前应用。

C 使用独立 2-bit 编码：0=FP32、1=FP16、2=BF16，3 非法；D 固定 FP32。运行格式是每事务控制，可连续变化。非法格式在顶层有效输入时断言；没有 ready 协议来等待一种不支持的格式。

待 SV 验收：全部合法混合对、保留编码、静态不支持的模式、相邻周期格式切换。格式细节和来源见 [Decode](../common/Decode.md)。
