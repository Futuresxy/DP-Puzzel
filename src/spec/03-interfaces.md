> 功能：汇总共用输入输出协议；范围：A/B/C、scale、metadata、逐笔 datatype 和 valid/last；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../cmodel/README.md)、[Chisel](../chisel/README.md)、[Verilog](../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# 接口与协议

~~状态：DP A/B/C 原子接收、FP32 C/D、无输出背压、会话模式固定的方向已确认；last 和全局统一复位已确认；端口逐位合同见 [DP 接口](dp/interface.md)。~~

**v1.2 当前定义：** 状态：DP A/B/C 原子接收、无输出背压、全局复位保持；v1.2 使用独立 A/B/C/scale datatype，取消模式会话锁定，last 只透传。完整可实现端口合同见 [DP 接口](dp/interface.md)。

## DP 输入

一次原子请求含 A、B、FP32 C 及当前格式所需 scale/metadata。只有 A、B、C 均有效且 scale/metadata 同步可用时，DP 才接收并执行；任一输入未到时，不接收新事务。A、B 以紧密排列的打包数据输入；TF32 使用高 19 位有效、低 13 位补零的 32 位容器，MXFP6 使用高 6 位数据加低 2 位零填充的 8 位槽，4 位格式每 byte 两个元素。完整映射见 [DP 容量合同](dp/layout-and-scales.md)。

解包输出采用固定 `E[9:0] / M[15:0] / S[3:0]`，普通 16 位原子块容纳 H1/Q2/E4，TF32 每 32 位容器一个元素；活动元素分类通过旁带保存，详见 [解包](dp/unpack.md)。

## scale 与 HiF4 metadata

scale 接口以每 16 个 E 元素一槽组织。T8H16Q32E64 有四个物理槽：MXFP8/6 四槽复制同一 32 项块 scale；HiF4 一个 64 项 scale 广播四槽；NVFP4 四槽独立；MXFP4 每两相邻槽共用一个 scale。HiF4 每槽携带 4 个 e1、2 个 e2 项，A/B 独立。

HiF4 e1/e2 均为 1 位，块 scale 为 8-bit E6M2 bias=48，编码见 [解包](dp/unpack.md)。~~MX/NV scale 的精确合同仍需冻结，不以空默认代替。~~

**v1.1 当前定义：** MX/NV scale 现采用 E8M0/非负 E4M3，与 E6M2 共用内部 E8M3；见 [scale](dp/scale.md)。

## 计算输出

所有浮点模式在 DP 内融合 C，经过最后的对齐和加法、LZD、RM 舍入与 norm，输出 FP32。~~INT8 可绕开浮点专用路径，但整数在 FP32 C/D 接口上的解释尚未决定。~~

~~**v1.1 当前定义：** INT8 会话将相同的 32 位 C/D 端口解释为 INT32，首版八级输出并按低 32 位回绕。~~

**v1.2 当前定义：** 每笔 INT8 请求把 C/D 的 32 位容器解释为 INT32，固定八级、低 32 位回绕；解释由同行 datatype 决定，无模式会话。

DP 输出包含 `valid`、结果和 `last`，不提供 ready。下游必须保证结果可接收。各输入源采用共同握手，避免 A/B/C 分开接收造成事务错配。

~~模式在一次活动会话中固定，收到 last 后等待最后输出，再切换格式。last 输入/输出均保留；只有接收的末请求结果输出后才允许切换格式。C 的来源及跨请求依赖由指令层保证，DP 仅执行本笔 A×B+C，见 [DP 接口](dp/interface.md)。~~

**v1.2 当前定义：** 每个请求可使用与前笔不同的合法格式；datatype 和派生 ctrl 同数据逐级传递。last 不停止接收、不触发排空，out_d_datatype 与结果同行。首版 A/B 同格式，浮点匹配 FP32 C、INT8 匹配 INT32 C；C 在 S5 解包，S1–S4 保持 raw32。

## 历史修订对照

以下为本次版本化时恢复的历史草案对照；删除线内容已被替代，不作为当前实现依据。较早内容尚无正式版本号，来源按真实提交或用户确认记录，不追认其为已批准合同。

- **last 与 C 边界**：~~DP 输出只有 valid 和结果（另有 last 候选）。~~ → **当前：**保留 out_valid/out_d/out_last；C 来源和指令依赖由上层处理。（来源：dba8ecf → 42350c5，用户确认）

## v1.2：详细端口、编码与历史参考

[DP 接口文档](dp/interface.md) 包含 K4/K8/K16 的固定总线宽、打包索引、各 datatype 编码、合法组合、原子 ready、模块 token 及时刻，以及 hw/legacy/PE_HQE 设计的参考与区别。scale 支持 E8M0/E4M3/E6M2，A/B 独立字段；当前不支持 A/B 混格式。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T15:13:43+08:00 | 历史记录 | 建立新版规格目录骨架与历史归档边界。 | [e8e07c2](https://github.com/Futuresxy/DP-Puzzel/commit/e8e07c2) |
| 未编号（追溯） | 2026-11-04T15:43:59+08:00 | 历史记录 | 记录 TensorCore/DP-Group/DP 首批架构、数值和时序要求。 | [76d31f2](https://github.com/Futuresxy/DP-Puzzel/commit/76d31f2) |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 更新相关数值/接口/流水定义，旧稿保留删除线。 | 用户架构图与补充；[总时间线](CHANGELOG.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 同步本轮接口、C 解包阶段、逐请求控制或资源/验证合同；保留被替代定义。 | 用户本轮要求及确认；[总时间线](CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 版本承接 | 承接v1.3架构号；正文合同及未决状态保持。 | 用户最终双向移位选择；[总时间线](CHANGELOG.md) |
