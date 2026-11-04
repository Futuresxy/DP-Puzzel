> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 规格版本与架构总时间线

~~状态：当前架构文档基线 v1.0；各文档保留已有确认/候选/待决状态，尚未进入新版实现。首次编号不构成新的架构批准。~~

~~状态：当前架构为 v1.1，按用户图重排共享八级流水及 sign/magnitude 接口；原候选/待决状态不因版本号自动批准。~~

~~状态：当前架构为 v1.2。逐请求 datatype 替代模式会话；C 在 S5 解包；补齐逐级数值、固定共享移位器与模块统计。仍仅 spec，原待决项不因版本号自动批准。~~

**v1.3 当前定义：** 本版采用 scale 后 LZD 计数与 S6 一次双向移位，所有规格同步承接 v1.3；同架构后续修订使用 v1.3.x，未决项不因版本号自动批准。

## 版本建立前的真实记录

以下提交发生时没有本轮正式版本号，按未编号历史保留，不倒填为 v0.x 或已冻结版本。

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T15:13:43+08:00 | 历史架构/规格记录 | 建立新版规格目录骨架与历史归档边界。 | [e8e07c2](https://github.com/Futuresxy/DP-Puzzel/commit/e8e07c2) |
| 未编号（追溯） | 2026-11-04T15:43:59+08:00 | 历史架构/规格记录 | 记录 TensorCore/DP-Group/DP 首批架构、数值和时序要求。 | [76d31f2](https://github.com/Futuresxy/DP-Puzzel/commit/76d31f2) |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史架构/规格记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史架构/规格记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |

## 正式版本记录

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 为当前全部规格补齐页首元信息与各自时间线；建立删除线修订规则、模板与版本索引，恢复关键旧稿对照。正文架构及确认状态承接 42350c5。 | 用户文档维护要求；[规则](document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | S2 并行乘/指数和/MAX；S3 幅值 RTZ/E pair；S4 树；S5 scale 后 sign/magnitude；S6+C 幅值 RTZ；S7 全部求和；S8 FP32 RNE/INT32 回绕。新增四份模块/资源/数值文档；全部宽度、树深、增长和补零由参数推导。同步全部文档架构号，层级及待决状态保持。 | 用户架构图及后续确认 |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 接口/周期控制修订 | A/B/C/scale 独立 datatype、首版 A/B 同格式；取消会话 FSM，逐请求 ctrl 与 last；C 解包移 S5；明确各级 SxIxFx/r/alpha/top-anchor、参数化 mux 共享移位器及功能块面积/功耗归属。新增三份文档，全套 29 份同步架构号。 | 用户本轮要求、两项确认及模块统计补充 |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 同架构讨论修订 | 新增组 SOP 规格化候选；推导合并移位/粗粒度界、signed 指数与 unsigned 差值；细化 S8 特殊结果 mux。当前架构仍 v1.2，无候选已自动批准。 | 用户本轮讨论 |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 用户选择scale后LZD仅计数、S6按z-d一次双向移位；明确原幅值/anchor/z接口、紧凑scale乘法及L9备用，双单向保留对照。 | 用户最终选择；本轮未提交中间草案保留删除线 |

## 当前文档版本索引

本表记录当前规格集合；后续只修改某文档时增加它的 `.x` 修订号，并同步本表和对应时间线。架构版本变化时按规则记录全套承接关系。具体源文件未建的状态在各页首保留。

v1.0 索引（已替代）：

| ~~文档~~ | ~~当前版本~~ | ~~功能~~ |
| --- | --- | --- |
| ~~[00-system-scope.md](00-system-scope.md)~~ | ~~v1.0~~ | ~~定义系统边界和设计目标~~ |
| ~~[01-numerics.md](01-numerics.md)~~ | ~~v1.0~~ | ~~定义数值语义与保留精度~~ |
| ~~[03-interfaces.md](03-interfaces.md)~~ | ~~v1.0~~ | ~~汇总共用输入输出协议~~ |
| ~~[04-timing-state.md](04-timing-state.md)~~ | ~~v1.0~~ | ~~定义周期和状态推进要求~~ |
| ~~[06-configuration.md](06-configuration.md)~~ | ~~v1.0~~ | ~~定义参数及其合法派生关系~~ |
| ~~[07-verification.md](07-verification.md)~~ | ~~v1.0~~ | ~~定义三实现共用验收合同~~ |
| ~~[08-implementation-ppa.md](08-implementation-ppa.md)~~ | ~~v1.0~~ | ~~定义实现交付与 PPA 评价规则~~ |
| ~~[CHANGELOG.md](CHANGELOG.md)~~ | ~~v1.0~~ | ~~记录整体架构与文档版本~~ |
| ~~[README.md](README.md)~~ | ~~v1.0~~ | ~~汇总新版规格入口和生效范围~~ |
| ~~[TEMPLATE.md](TEMPLATE.md)~~ | ~~v1.0~~ | ~~提供新规格模板~~ |
| ~~[document-control.md](document-control.md)~~ | ~~v1.0~~ | ~~维护版本与修订规则~~ |
| ~~[dp-group/README.md](dp-group/README.md)~~ | ~~v1.0~~ | ~~定义广播计算组规格~~ |
| ~~[dp/README.md](dp/README.md)~~ | ~~v1.0~~ | ~~汇总 DP 主方案与设计入口~~ |
| ~~[dp/control.md](dp/control.md)~~ | ~~v1.0~~ | ~~定义 DP 会话状态与有效位推进~~ |
| ~~[dp/independent-align.md](dp/independent-align.md)~~ | ~~v1.0~~ | ~~记录独立移位对齐对比方案~~ |
| ~~[dp/interface.md](dp/interface.md)~~ | ~~v1.0~~ | ~~定义 DP 请求及端口合同~~ |
| ~~[dp/layout-and-scales.md](dp/layout-and-scales.md)~~ | ~~v1.0~~ | ~~定义 DP 容量与输入布局~~ |
| ~~[dp/pipeline.md](dp/pipeline.md)~~ | ~~v1.0~~ | ~~定义分组共享 DP 的流水候选~~ |
| ~~[dp/shared-align.md](dp/shared-align.md)~~ | ~~v1.0~~ | ~~定义分组共享对齐微架构~~ |
| ~~[dp/special-values.md](dp/special-values.md)~~ | ~~v1.0~~ | ~~定义浮点分类与特殊值传播~~ |
| ~~[dp/unpack.md](dp/unpack.md)~~ | ~~v1.0~~ | ~~定义固定 E/M/S 解包数值布局~~ |
| ~~[tensorcore/README.md](tensorcore/README.md)~~ | ~~v1.0~~ | ~~定义 TensorCore 阵列规格~~ |

v1.1 索引（已替代）：

| ~~文档~~ | ~~当前版本~~ | ~~功能~~ |
| --- | --- | --- |
| ~~[00-system-scope.md](00-system-scope.md)~~ | ~~v1.1~~ | ~~定义系统边界和设计目标~~ |
| ~~[01-numerics.md](01-numerics.md)~~ | ~~v1.1~~ | ~~定义数值语义与保留精度~~ |
| ~~[03-interfaces.md](03-interfaces.md)~~ | ~~v1.1~~ | ~~汇总共用输入输出协议~~ |
| ~~[04-timing-state.md](04-timing-state.md)~~ | ~~v1.1~~ | ~~定义周期和状态推进要求~~ |
| ~~[06-configuration.md](06-configuration.md)~~ | ~~v1.1~~ | ~~定义参数及其合法派生关系~~ |
| ~~[07-verification.md](07-verification.md)~~ | ~~v1.1~~ | ~~定义三实现共用验收合同~~ |
| ~~[08-implementation-ppa.md](08-implementation-ppa.md)~~ | ~~v1.1~~ | ~~定义实现交付与 PPA 评价规则~~ |
| ~~[CHANGELOG.md](CHANGELOG.md)~~ | ~~v1.1~~ | ~~记录整体架构与文档版本~~ |
| ~~[README.md](README.md)~~ | ~~v1.1~~ | ~~汇总新版规格入口和生效范围~~ |
| ~~[TEMPLATE.md](TEMPLATE.md)~~ | ~~v1.1~~ | ~~提供新规格模板~~ |
| ~~[document-control.md](document-control.md)~~ | ~~v1.1~~ | ~~维护版本与修订规则~~ |
| ~~[dp-group/README.md](dp-group/README.md)~~ | ~~v1.1~~ | ~~定义广播计算组规格~~ |
| ~~[dp/README.md](dp/README.md)~~ | ~~v1.1~~ | ~~汇总 DP 主方案与设计入口~~ |
| ~~[dp/control.md](dp/control.md)~~ | ~~v1.1~~ | ~~定义 DP 会话状态与有效位推进~~ |
| ~~[dp/independent-align.md](dp/independent-align.md)~~ | ~~v1.1~~ | ~~记录独立移位对齐对比方案~~ |
| ~~[dp/interface.md](dp/interface.md)~~ | ~~v1.1~~ | ~~定义 DP 请求及端口合同~~ |
| ~~[dp/layout-and-scales.md](dp/layout-and-scales.md)~~ | ~~v1.1~~ | ~~定义 DP 容量与输入布局~~ |
| ~~[dp/pipeline.md](dp/pipeline.md)~~ | ~~v1.1~~ | ~~定义分组共享 DP 的流水候选~~ |
| ~~[dp/shared-align.md](dp/shared-align.md)~~ | ~~v1.1~~ | ~~定义分组共享对齐微架构~~ |
| ~~[dp/special-values.md](dp/special-values.md)~~ | ~~v1.1~~ | ~~定义浮点分类与特殊值传播~~ |
| ~~[dp/unpack.md](dp/unpack.md)~~ | ~~v1.1~~ | ~~定义固定 E/M/S 解包数值布局~~ |
| ~~[tensorcore/README.md](tensorcore/README.md)~~ | ~~v1.1~~ | ~~定义 TensorCore 阵列规格~~ |
| ~~[dp/multiplier-sharing.md](dp/multiplier-sharing.md)~~ | ~~v1.1~~ | ~~尾数乘法器组共享与路由~~ |
| ~~[dp/module-hierarchy.md](dp/module-hierarchy.md)~~ | ~~v1.1~~ | ~~三层模块所有权与未来 S6 专用源接入~~ |
| ~~[dp/numeric-layout.md](dp/numeric-layout.md)~~ | ~~v1.1~~ | ~~参数位宽/符号幅值/全局 anchor~~ |
| ~~[dp/scale.md](dp/scale.md)~~ | ~~v1.1~~ | ~~E8M3 scale 与 bias~~ |

~~v1.2 / v1.2.1 索引（已替代）：~~

| ~~文档~~ | ~~当前版本~~ | ~~功能~~ |
| --- | --- | --- |
| ~~[00-system-scope.md](00-system-scope.md)~~ | ~~v1.2~~ | ~~定义系统边界和设计目标~~ |
| ~~[01-numerics.md](01-numerics.md)~~ | ~~v1.2~~ | ~~定义数值语义与保留精度~~ |
| ~~[03-interfaces.md](03-interfaces.md)~~ | ~~v1.2~~ | ~~汇总共用输入输出协议~~ |
| ~~[04-timing-state.md](04-timing-state.md)~~ | ~~v1.2~~ | ~~定义周期和状态推进要求~~ |
| ~~[06-configuration.md](06-configuration.md)~~ | ~~v1.2~~ | ~~定义参数及其合法派生关系~~ |
| ~~[07-verification.md](07-verification.md)~~ | ~~v1.2~~ | ~~定义三实现共用验收合同~~ |
| ~~[08-implementation-ppa.md](08-implementation-ppa.md)~~ | ~~v1.2~~ | ~~定义实现交付与 PPA 评价规则~~ |
| ~~[CHANGELOG.md](CHANGELOG.md)~~ | ~~v1.2~~ | ~~维护整体架构与文档版本时间线~~ |
| ~~[CHANGELOG.md](CHANGELOG.md)~~ | ~~v1.2.1~~ | ~~维护整体架构与文档版本时间线~~ |
| ~~[README.md](README.md)~~ | ~~v1.2~~ | ~~汇总新版规格入口和生效范围~~ |
| ~~[README.md](README.md)~~ | ~~v1.2.1~~ | ~~汇总新版规格入口和生效范围~~ |
| ~~[TEMPLATE.md](TEMPLATE.md)~~ | ~~v1.2~~ | ~~提供新规格的固定格式模板~~ |
| ~~[document-control.md](document-control.md)~~ | ~~v1.2~~ | ~~定义规格版本和历史修订规则~~ |
| ~~[dp/README.md](dp/README.md)~~ | ~~v1.2~~ | ~~汇总 DP 主方案与设计入口~~ |
| ~~[dp/README.md](dp/README.md)~~ | ~~v1.2.1~~ | ~~汇总 DP 主方案与设计入口~~ |
| ~~[dp/control.md](dp/control.md)~~ | ~~v1.2~~ | ~~定义 DP 逐请求控制与有效位推进~~ |
| ~~[dp/independent-align.md](dp/independent-align.md)~~ | ~~v1.2~~ | ~~记录独立移位对齐对比方案~~ |
| ~~[dp/interface.md](dp/interface.md)~~ | ~~v1.2~~ | ~~定义 DP 顶层和模块接口~~ |
| ~~[dp/layout-and-scales.md](dp/layout-and-scales.md)~~ | ~~v1.2~~ | ~~定义 DP 容量与输入布局~~ |
| ~~[dp/module-hierarchy.md](dp/module-hierarchy.md)~~ | ~~v1.2~~ | ~~定义 DP 模块层级与未来 S6 接入合同~~ |
| ~~[dp/multiplier-sharing.md](dp/multiplier-sharing.md)~~ | ~~v1.2~~ | ~~定义尾数乘法器共享和模式路由~~ |
| ~~[dp/numeric-layout.md](dp/numeric-layout.md)~~ | ~~v1.2~~ | ~~推导逐级位宽和统一对齐坐标~~ |
| ~~[dp/numeric-layout.md](dp/numeric-layout.md)~~ | ~~v1.2.1~~ | ~~推导逐级位宽和统一对齐坐标~~ |
| ~~[dp/pipeline.md](dp/pipeline.md)~~ | ~~v1.2~~ | ~~定义分组共享 DP 的流水候选~~ |
| ~~[dp/pipeline.md](dp/pipeline.md)~~ | ~~v1.2.1~~ | ~~定义分组共享 DP 的流水候选~~ |
| ~~[dp/resource-accounting.md](dp/resource-accounting.md)~~ | ~~v1.2~~ | ~~定义可统计的功能模块边界~~ |
| ~~[dp/resource-accounting.md](dp/resource-accounting.md)~~ | ~~v1.2.1~~ | ~~定义可统计的功能模块边界~~ |
| ~~[dp/scale.md](dp/scale.md)~~ | ~~v1.2~~ | ~~定义 scale 统一解包和 bias 处理~~ |
| ~~[dp/scale.md](dp/scale.md)~~ | ~~v1.2.1~~ | ~~定义 scale 统一解包和 bias 处理~~ |
| ~~[dp/shared-align.md](dp/shared-align.md)~~ | ~~v1.2~~ | ~~定义分组共享对齐微架构~~ |
| ~~[dp/shifter-sharing.md](dp/shifter-sharing.md)~~ | ~~v1.2~~ | ~~定义固定物理移位器的 mux 复用~~ |
| ~~[dp/special-values.md](dp/special-values.md)~~ | ~~v1.2~~ | ~~定义浮点分类与特殊值传播~~ |
| ~~[dp/special-values.md](dp/special-values.md)~~ | ~~v1.2.1~~ | ~~定义浮点分类与特殊值传播~~ |
| ~~[dp/stage-formats.md](dp/stage-formats.md)~~ | ~~v1.2~~ | ~~列出每级数值出口的定点格式与指数范围~~ |
| ~~[dp/unpack.md](dp/unpack.md)~~ | ~~v1.2~~ | ~~定义固定 E/M/S 解包数值布局~~ |
| ~~[dp-group/README.md](dp-group/README.md)~~ | ~~v1.2~~ | ~~定义广播计算组规格~~ |
| ~~[tensorcore/README.md](tensorcore/README.md)~~ | ~~v1.2~~ | ~~定义 TensorCore 阵列规格~~ |
| ~~[dp/group-normalization-options.md](dp/group-normalization-options.md)~~ | ~~v1.2.1~~ | ~~组实际指数、合并移位与粗粒度检测候选~~ |

v1.3 当前索引：

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [00-system-scope.md](00-system-scope.md) | v1.3 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.3 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.3 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.3 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.3 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.3 | 定义三实现共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.3 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.3 | 维护整体架构与文档版本时间线 |
| [README.md](README.md) | v1.3 | 汇总新版规格入口和生效范围 |
| [TEMPLATE.md](TEMPLATE.md) | v1.3 | 提供新规格的固定格式模板 |
| [document-control.md](document-control.md) | v1.3 | 定义规格版本和历史修订规则 |
| [dp-group/README.md](dp-group/README.md) | v1.3 | 定义广播计算组规格 |
| [dp/README.md](dp/README.md) | v1.3 | 汇总 DP 主方案与设计入口 |
| [dp/control.md](dp/control.md) | v1.3 | 定义 DP 逐请求控制与有效位推进 |
| [dp/group-normalization-options.md](dp/group-normalization-options.md) | v1.3 | 定义scale后LZD计数与S6合并双向对齐 |
| [dp/independent-align.md](dp/independent-align.md) | v1.3 | 记录独立移位对齐对比方案 |
| [dp/interface.md](dp/interface.md) | v1.3 | 定义 DP 顶层和模块接口 |
| [dp/layout-and-scales.md](dp/layout-and-scales.md) | v1.3 | 定义 DP 容量与输入布局 |
| [dp/module-hierarchy.md](dp/module-hierarchy.md) | v1.3 | 定义 DP 模块层级与未来 S6 接入合同 |
| [dp/multiplier-sharing.md](dp/multiplier-sharing.md) | v1.3 | 定义尾数乘法器共享和模式路由 |
| [dp/numeric-layout.md](dp/numeric-layout.md) | v1.3 | 推导逐级位宽和统一对齐坐标 |
| [dp/pipeline.md](dp/pipeline.md) | v1.3 | 定义分组共享 DP 的流水候选 |
| [dp/resource-accounting.md](dp/resource-accounting.md) | v1.3 | 定义可统计的功能模块边界 |
| [dp/scale.md](dp/scale.md) | v1.3 | 定义 scale 统一解包和 bias 处理 |
| [dp/shared-align.md](dp/shared-align.md) | v1.3 | 定义分组共享对齐微架构 |
| [dp/shifter-sharing.md](dp/shifter-sharing.md) | v1.3 | 定义固定物理移位器的 mux 复用 |
| [dp/special-values.md](dp/special-values.md) | v1.3 | 定义浮点分类与特殊值传播 |
| [dp/stage-formats.md](dp/stage-formats.md) | v1.3 | 列出每级数值出口的定点格式与指数范围 |
| [dp/unpack.md](dp/unpack.md) | v1.3 | 定义固定 E/M/S 解包数值布局 |
| [tensorcore/README.md](tensorcore/README.md) | v1.3 | 定义 TensorCore 阵列规格 |

新条目继续追加时间线。已替代的正文保留删除线，历史版本和历史时间不能被删除；详见 [版本与修订规则](document-control.md)。

## v1.1 补充的用户确认

最终 FP32 仅 RNE；INT8→INT32 采用回绕并在验证中记录 overflow；S5 组输出为独立符号/幅值，S6 对幅值 RTZ；所有宽度/补零/树深从参数对象推导。模块层级为 T1H2Q4E8→T2H4Q8E16→H16Q32E64（T8），当前八级；未来 Q/E/QE 仅从 S6 接入点规划，扩展 profile 可另定额外 1–2 级。

## v1.3 架构变更范围

2026-11-04 21:00:06 +08:00：用户明确在scale乘法后做LZD，并最终选择只产生计数z、S6得到E_max后按z-d一次双向移位。两段单向移位是本轮中间草案，尚未形成独立提交；保留其删除线记录和后续PPA/时序对照。

S5原幅值/原anchor新增z字段，S6实际指数MAX与净位移，可能改变相对v1.2的RTZ结果；整套30份spec同步v1.3。实质变更包括scale、S5/S6数值、内部接口、资源/时序与验收；其余正文只承接版本。默认L8，必要时L9检测/指数准备备用；未运行CModel/RTL/EDA，不声称双向方案PPA已胜出。

## 本轮未提交草案对照：v1.3 架构变更范围

~~## v1.3 架构变更范围~~

~~2026-11-04 20:52:39 +08:00：用户确认“做完 scale 乘法后，再做 LZD、重新处理 anchor、移位 SOP”。组浮点出口从容器坐标变为真实最高位坐标，S6 RTZ网格可能改变，故升架构版本。~~

~~实质更新涉及 DP 的规格化、scale、逐级格式、流水、数值、内部接口、乘法/移位共享、模块归属和验证配置；其余文档只承接架构号。全套30份文件更新元信息/时间线，未实现文件仍明确未建。共享乘法具体门级组织为待综合比较的建议；默认L8，允许时序必要时独立L9规格化profile。未开始CModel/RTL/EDA。~~

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 初建 | 建立版本前记录、正式版本时间线及当前文档版本索引；本文件无算术/流水架构变更。 | 用户文档维护要求 |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 记录本轮新流水、源码参考边界与 26 份文档版本索引；旧 v1.0 索引保留删除线。 | 用户确认 |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 记录 v1.2 架构修订和 29 份文档索引；v1.0/v1.1 索引与真实时间保留。 | 用户本轮要求及确认；[总时间线](CHANGELOG.md) |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 索引更新 | 当前 30 份 spec；受影响文档修订为 v1.2.1，其余保留 v1.2。记录候选而不更改生效架构。 | 用户本轮讨论 |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 全套30份文档更新v1.3；当前选择为scale后计数与S6双向移位，未提交中间草案保留对照，无实现/EDA。 | 用户最终双向移位选择；[总时间线](CHANGELOG.md) |
