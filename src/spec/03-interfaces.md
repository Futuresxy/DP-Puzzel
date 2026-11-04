# 接口与协议

状态：DP A/B/C 原子接收、FP32 C/D、无输出背压、会话模式固定的方向已确认；last 和全局统一复位已确认；端口逐位合同见 [DP 接口](dp/interface.md)。

## DP 输入

一次原子请求含 A、B、FP32 C 及当前格式所需 scale/metadata。只有 A、B、C 均有效且 scale/metadata 同步可用时，DP 才接收并执行；任一输入未到时，不接收新事务。A、B 以紧密排列的打包数据输入；TF32 使用高 19 位有效、低 13 位补零的 32 位容器，MXFP6 使用高 6 位数据加低 2 位零填充的 8 位槽，4 位格式每 byte 两个元素。完整映射见 [DP 容量合同](dp/layout-and-scales.md)。

解包输出采用固定 `E[9:0] / M[15:0] / S[3:0]`，普通 16 位原子块容纳 H1/Q2/E4，TF32 每 32 位容器一个元素；活动元素分类通过旁带保存，详见 [解包](dp/unpack.md)。

## scale 与 HiF4 metadata

scale 接口以每 16 个 E 元素一槽组织。T8H16Q32E64 有四个物理槽：MXFP8/6 四槽复制同一 32 项块 scale；HiF4 一个 64 项 scale 广播四槽；NVFP4 四槽独立；MXFP4 每两相邻槽共用一个 scale。HiF4 每槽携带 4 个 e1、2 个 e2 项，A/B 独立。

HiF4 e1/e2 均为 1 位，块 scale 为 8-bit E6M2 bias=48，编码见 [解包](dp/unpack.md)。MX/NV scale 的精确合同仍需冻结，不以空默认代替。

## 计算输出

所有浮点模式在 DP 内融合 C，经过最后的对齐和加法、LZD、RM 舍入与 norm，输出 FP32。INT8 可绕开浮点专用路径，但整数在 FP32 C/D 接口上的解释尚未决定。

DP 输出包含 `valid`、结果和 `last`，不提供 ready。下游必须保证结果可接收。各输入源采用共同握手，避免 A/B/C 分开接收造成事务错配。

模式在一次活动会话中固定，收到 last 后等待最后输出，再切换格式。last 输入/输出均保留；只有接收的末请求结果输出后才允许切换格式。C 的来源及跨请求依赖由指令层保证，DP 仅执行本笔 A×B+C，见 [DP 接口](dp/interface.md)。
