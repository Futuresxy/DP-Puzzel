# 接口与协议

状态：DP A/B/C 原子接收、FP32 C/D、无输出背压、会话模式固定的方向已确认；端口逐位合同见 [DP 接口](dp/interface.md)。

## DP 输入

一次原子请求含 A、B、FP32 C 及当前格式所需 scale/metadata。只有 A、B、C 均有效且 scale/metadata 同步可用时，DP 才接收并执行；任一输入未到时，不接收新事务。A、B 以紧密排列的打包数据输入；TF32 使用高 19 位有效、低 13 位补零的 32 位容器，MXFP6 使用高 6 位数据加低 2 位零填充的 8 位槽，4 位格式每 byte 两个元素。完整映射见 [DP 容量合同](dp/layout-and-scales.md)。

## scale 与 HiF4 metadata

scale 接口以每 16 个 E 元素一槽组织。T8H16Q32E64 有四个物理槽：MXFP8/6 四槽复制同一 32 项块 scale；HiF4 一个 64 项 scale 广播四槽；NVFP4 四槽独立；MXFP4 每两相邻槽共用一个 scale。HiF4 每槽携带 4 个 e1、2 个 e2 项，A/B 独立。

scale 编码位宽和值域、HiF4 字段位宽及字段语义仍由数值格式合同定义；接口结构已明确，不以空默认或旧实现位宽替代。

## 计算输出

所有浮点模式在 DP 内融合 C，经过最后的对齐和加法、LZD、RM 舍入与 norm，输出 FP32。INT8 可绕开浮点专用路径，但整数在 FP32 C/D 接口上的解释尚未决定。

DP 输出只有 `valid` 和结果（另有 last 候选），不提供 ready。下游必须保证结果可接收。各输入源采用共同握手，避免 A/B/C 分开接收造成事务错配。

模式在一次活动会话中固定，收到 last 后等待最后输出，再切换格式。`last` 是否必要、跨事务累加 C→D 依赖由 [DP 接口 spec](dp/interface.md) 留待继续讨论。
