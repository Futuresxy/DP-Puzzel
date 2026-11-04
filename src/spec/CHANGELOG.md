> 功能：维护整体架构与文档版本时间线；范围：当前全部新版 spec 的版本索引和变更依据；版本：v1.0；修改时间：2026-11-04 17:36:11 +08:00；对应代码：无运行时代码；实现与报告引用此处规格快照。

# 规格版本与架构总时间线

状态：当前架构文档基线 v1.0；各文档保留已有确认/候选/待决状态，尚未进入新版实现。首次编号不构成新的架构批准。

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

## 当前文档版本索引

本表记录当前规格集合；后续只修改某文档时增加它的 `.x` 修订号，并同步本表和对应时间线。架构版本变化时按规则记录全套承接关系。具体源文件未建的状态在各页首保留。

| 文档 | 当前版本 | 功能 |
| --- | --- | --- |
| [00-system-scope.md](00-system-scope.md) | v1.0 | 定义系统边界和设计目标 |
| [01-numerics.md](01-numerics.md) | v1.0 | 定义数值语义与保留精度 |
| [03-interfaces.md](03-interfaces.md) | v1.0 | 汇总共用输入输出协议 |
| [04-timing-state.md](04-timing-state.md) | v1.0 | 定义周期和状态推进要求 |
| [06-configuration.md](06-configuration.md) | v1.0 | 定义参数及其合法派生关系 |
| [07-verification.md](07-verification.md) | v1.0 | 定义三实现共用验收合同 |
| [08-implementation-ppa.md](08-implementation-ppa.md) | v1.0 | 定义实现交付与 PPA 评价规则 |
| [CHANGELOG.md](CHANGELOG.md) | v1.0 | 记录整体架构与文档版本 |
| [README.md](README.md) | v1.0 | 汇总新版规格入口和生效范围 |
| [TEMPLATE.md](TEMPLATE.md) | v1.0 | 提供新规格模板 |
| [document-control.md](document-control.md) | v1.0 | 维护版本与修订规则 |
| [dp-group/README.md](dp-group/README.md) | v1.0 | 定义广播计算组规格 |
| [dp/README.md](dp/README.md) | v1.0 | 汇总 DP 主方案与设计入口 |
| [dp/control.md](dp/control.md) | v1.0 | 定义 DP 会话状态与有效位推进 |
| [dp/independent-align.md](dp/independent-align.md) | v1.0 | 记录独立移位对齐对比方案 |
| [dp/interface.md](dp/interface.md) | v1.0 | 定义 DP 请求及端口合同 |
| [dp/layout-and-scales.md](dp/layout-and-scales.md) | v1.0 | 定义 DP 容量与输入布局 |
| [dp/pipeline.md](dp/pipeline.md) | v1.0 | 定义分组共享 DP 的流水候选 |
| [dp/shared-align.md](dp/shared-align.md) | v1.0 | 定义分组共享对齐微架构 |
| [dp/special-values.md](dp/special-values.md) | v1.0 | 定义浮点分类与特殊值传播 |
| [dp/unpack.md](dp/unpack.md) | v1.0 | 定义固定 E/M/S 解包数值布局 |
| [tensorcore/README.md](tensorcore/README.md) | v1.0 | 定义 TensorCore 阵列规格 |

新条目继续追加时间线。已替代的正文保留删除线，历史版本和历史时间不能被删除；详见 [版本与修订规则](document-control.md)。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 初建 | 建立版本前记录、正式版本时间线及当前文档版本索引；本文件无算术/流水架构变更。 | 用户文档维护要求 |
