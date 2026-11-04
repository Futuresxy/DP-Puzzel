> 功能：定义 DP 请求及端口合同；范围：原子 A/B/C 接收、C 合并、输出及 last；版本：v1.1；修改时间：2026-11-04 19:12:59 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# DP 接口、输出与握手

状态：A/B/C 原子接收、无输出背压、会话模式固定、保留输入/输出 last、全局统一复位及浮点 FP32 C/D 已确认。~~精确握手表达式是下列候选合同；RM、INT8 C/D 编码和 scale/metadata 字段仍需闭合。~~

**v1.1 当前定义：** 原子握手表达式仍为候选；浮点 RNE、INT32 C/D 与回绕、scale 编码已明确；剩余数值边界及参数合法性继续完善。

## 计算边界与输出

每个有效请求携带完整配置 K 的 A、B、C 及适用 scale/metadata。浮点 DP 在内部完成缩放点积、部分和归约、与 FP32 C 对齐相加及 FP32 输出转换，数学目标为 `D = round_fp32(C + scaled_dot(A,B))`。有限位宽的实际计算顺序按逐级数值合同定义；该数学式本身不承诺无限精度点积只舍入一次。A/B scale 只作用于点积，不缩放 C。

DP 使用本笔携带的 C，不区分初始加数或前序结果，不自行反馈 D，也不维护跨请求 accumulator。C 的取数、指令级依赖及 C→D RAW 由上层保证，不再作为 DP 数值或控制合同的未决项。

所有浮点模式输出 FP32，内部 25/35/约 37 位保留目标另行定义。每笔接收对应一个结果；包括 NaN/Inf 在内的特殊结果保持同一模式的固定延迟，详见 [特殊值](special-values.md)。~~INT8 仍执行整数乘积规约及加 C；若采用纯整数 C/D 可跳过浮点对齐、归一化和舍入，其 C/D 编码和溢出规则待定。~~

**v1.1 当前定义：** INT8 采用 signed INT8×INT8+INT32 C，输出 INT32。首版与浮点共用八级寄存边界，S8 输出低 32 位回绕；溢出条件记录到验证 trace，不新增异常端口。

## 端口合同

| 信号 | 方向 | 合同 |
| --- | --- | --- |
| `clock` / `reset` | 入 | 所有 DP 子模块共用全局复位；同步方式/有效极性见控制文档 |
| `in_a_valid`, `in_b_valid`, `in_c_valid` | 入 | 源侧有效；scale/metadata 与所属 A/B payload 同步有效 |
| `out_a_ready`, `out_b_ready`, `out_c_ready` | 出 | 原子接收候选采用三路同拍握手，见下式 |
| `in_mode` | 入 | 首请求锁存本会话模式，后续请求保持同一模式；配置方式候选见控制文档 |
| `in_a`, `in_b` | 入 | 紧密打包，外部布局见 [容量合同](layout-and-scales.md)，内部固定字段见 [解包](unpack.md) |
| ~~`in_scale_a`, `in_scale_b`~~ | ~~入~~ | ~~每 16 E 元素一槽；字段编码待定~~ |
| `in_scale_a`, `in_scale_b` | 入 | 每 16 E 元素一槽，八位 E8M0/E4M3/E6M2，内部统一 E8M3 |
| `in_hif4_e1_a/b`, `in_hif4_e2_a/b` | 入 | 每 16 E 元素含 4 个 1-bit e1 和 2 个 1-bit e2，按每 4/8 项共享 |
| ~~`in_c`~~ | ~~入~~ | ~~每请求一个 FP32 加数；INT8 下的位解释待定~~ |
| `in_c` | 入 | 浮点会话为 FP32；INT8 会话相同 32 位端口按二补码 INT32 解释 |
| `in_last` | 入 | 必须保留；本会话最后一笔请求，与该笔原子输入绑定 |
| `out_valid` | 出 | 结果有效，无 `out_ready`；下游保证接收 |
| ~~`out_d`~~ | ~~出~~ | ~~FP32 D；INT8 下的位解释待定~~ |
| `out_d` | 出 | 浮点会话为 FP32、仅 RNE；INT8 会话为二补码 INT32 回绕结果 |
| `out_last` | 出 | 输入 last 的对应输出标记；仅在 `out_valid=1` 时有效 |

目前不新增异常状态端口。异常条件与结果值先在数值合同中定义；是否输出逐请求 IEEE 异常 flags 另行决定。

## 原子握手候选

```text
all_valid = in_a_valid & in_b_valid & in_c_valid
accept_enable = 非复位 & 状态允许接收 & mode 合法且符合会话约束
out_a_ready = out_b_ready = out_c_ready = accept_enable & all_valid
req_fire = accept_enable & all_valid
```

该候选中 ready 只在三份操作数同时可接收时拉高，每个源按自己的 valid/ready 观察到的 transfer 都等于 `req_fire`，不会出现部分接收。源不能等待 ready 才产生 valid；valid 拉高而未握手时，源保持 payload（含 scale/metadata、mode、last）稳定。scale/meta 随 A/B 有效，无独立握手或独立队列。

输入不齐形成 bubble；已接收请求仍推进，不因取数停顿延长延迟。输出固定延迟且无背压，DP-Group/测试环境必须在每次 `out_valid` 时接收。

## 模式固定与 last

首个 `req_fire` 锁定模式，后续请求使用同一模式。`req_fire & in_last` 关闭本会话输入并进入排空；未经握手的 last 无效。只有 `out_valid & out_last` 出现、最后结果输出完成后，才能接受下一会话的新模式。

输入 bubble 或流水暂时为空都不结束会话；未提交 last 时继续保持模式。last 表达取数流的结束边界并随结果传递，不触发额外累加，也不改变本请求的 A×B+C 计算。

## v1.1：基本组内部接口

T2H4Q8E16 的 S5 接口采用独立 negative、无符号 magnitude、anchor/F、zero/special、valid/last。S6 对幅值向零截断后恢复补码，S7 才规约所有组与 C。位宽及字段数量由 [数值合同](numeric-layout.md) 和构建参数派生，内部接口不改变外部原子握手与模式会话规则。

## 历史修订对照

以下为本次版本化时恢复的历史草案对照；删除线内容已被替代，不作为当前实现依据。较早内容尚无正式版本号，来源按真实提交或用户确认记录，不追认其为已批准合同。

- **last**：~~标记数据流中本次会话/帧的末项候选；是否必需待确认。~~ → **当前：**in_last 必须保留，与原子请求绑定，并传递为 out_last。（来源：dba8ecf → 42350c5，用户确认）

- **C 来源**：~~C 是每个独立点积请求的初始加数，还是流中逐项累加的前序结果，仍待确认。~~ → **当前：**DP 只使用本笔 C 计算缩放点积加 C；取数与依赖由指令层保证。（来源：dba8ecf → 42350c5，旧待决问题摘要）

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](../document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 补充 v1.1 相关资源、数值或验证合同。 | 用户架构图与补充；[总时间线](../CHANGELOG.md) |
