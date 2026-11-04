> 功能：汇总新版规格入口和生效范围；范围：TensorCore、DP-Group、DP 及共用合同；版本：v1.2.1；修改时间：2026-11-04 20:17:40 +08:00；对应代码：[CModel](../cmodel/README.md)、[Chisel](../chisel/README.md)、[Verilog](../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# 多精度 TensorCore 规格

状态：**第一批架构要求已确认，详细合同继续完善；尚未进入实现**。本轮依据为用户 2026-11-04 的需求，不沿用旧 PE 的结构、数值和周期合同。

## 三层设计入口

| 层级 | 文档 | 已确认要求 |
| --- | --- | --- |
| TensorCore | [阵列组织](tensorcore/README.md) | 16×4 个 DP；四个 DP-Group 沿竖直方向拼接 |
| DP-Group | [广播计算组](dp-group/README.md) | 每组 4×4 个 DP，组内广播，DP 间无脉动 |
| DP | [多精度点积](dp/README.md) | FP16 K4 基本组 T2H4Q8E16；并行组合成 K8/K16；分组共享是当前主方案 |

支持 TF32（每元素输入容器 32 位）、FP16、BF16、MXFP8、MXFP6、MXFP4、NVFP4、HiF4 和 INT8；暂不支持 HiF8。~~INT8 的计算并行度与 MXFP8 相同，可旁路浮点专用级；保留整数乘法/累加/加 C，精确延迟由省去浮点对齐/归一化/舍入后的流水切分决定。~~

**v1.1 当前定义：** INT8 的计算并行度与 MXFP8 相同，C/D 为 INT32；首版共用八级寄存边界，S8 回绕输出，浮点只采用 RNE。

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


## 文档版本与历史维护入口

~~当前文档基线为 **v1.0**。同一架构内使用 v1.0.x 修订；架构变更使用新 vM.N 并注明时间、原因与影响。版本号不替代每项定义的确认状态。~~

~~**v1.1 当前定义：** 当前架构文档为 **v1.1**；v1.0 的结构/数值修订已保留删除线与时间线。后续同架构修订使用 v1.1.x，版本号不替代确认/候选/待决状态。~~

**v1.2 当前定义：** 当前整套架构文档为 **v1.2**；独立 datatype、C 解包移到 S5、逐请求控制替代会话锁定，均保留删除线历史。接口/数值/资源合同具体状态见各页；同架构修订为 v1.2.x。

- [版本与修订规则](document-control.md)：页首功能/范围/时间/代码映射、删除线修订和架构时间线。
- [规格总时间线与版本索引](CHANGELOG.md)：当前每份文档版本与历史来源。
- [新规格模板](TEMPLATE.md)：后续模块合同的固定格式。

## v1.1 共享八级架构入口

按用户图将指数和/尾数乘法并行至 S2，S3 共享幅值对齐，S4 lane 树，S5 两 lane/scale 后输出独立符号/幅值，S6 组+C 幅值向零对齐，S7 全部求和，S8 FP32 RNE/INT32 回绕。新增 [乘法器共享](dp/multiplier-sharing.md)、[逐级数值布局](dp/numeric-layout.md) 和 [scale/bias](dp/scale.md)。全部宽度、树深与增长由 Chisel 模块参数对象和同源配置推导，当前仍仅 spec。

## v1.1：三层模块所有权

主配置层级为 `T1H2Q4E8 → T2H4Q8E16 → H16Q32E64（T8）`，见 [模块层级与 S6 扩展](dp/module-hierarchy.md)。先全面定义当前八级共享架构和数值/接口，再开发 CModel；未来 Q/E/QE 专用源及额外 1–2 级只记录扩展边界。

## v1.2：接口与功能模块合同

本轮重点入口：[DP 接口定义](dp/interface.md)、[逐请求控制](dp/control.md)、[每级 SxIxFx/anchor/SOP](dp/stage-formats.md)、[固定共享移位器](dp/shifter-sharing.md)、[功能块面积与功耗归属](dp/resource-accounting.md)。A/B 独立 datatype 但首版仅同格式；scale 保留 E8M0/E4M3/E6M2；C 在 S5 解包；所有格式固定 L=8。last 保留为逐请求上层标记，不再限制换型。

## v1.2.1 文档补充

新增 [组 SOP 实际指数与对齐候选](dp/group-normalization-options.md)，比较逐组 LZD、合并移位与粗粒度检测；明确 signed anchor/unsigned 对齐差值及最终特殊值 mux。本次为同架构讨论修订，当前 v1.2 算术/流水路径没有切换，候选尚待选定。

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
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 讨论/说明补充 | 记录组实际指数候选及对应数值、特殊值或资源边界；不改变 v1.2 主路径。 | 用户 LZD/指数/特殊值讨论；[总时间线](CHANGELOG.md) |
