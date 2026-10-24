# 功耗输入、DC 交接与回执

状态：`planned` 文本契约；本轮没有实现 JSON Schema、输入解析器、回执生产器或 runner。配置样例不构成 PASS。所有 hash 为原字节 SHA-256；所有 ID 显式，拒绝 latest、glob、缺失字段和未知单位。

## 1. RTL 与真实测试数据

接收已通过的 `export_id`，复用 `scripts/rtl_gate.py` 的 `verify_export` 语义与 [DC 输入契约](../dc_syn/input-contract.md)所关联的 v1 回执。power 不手写 manifest / verification 的成功字段，也不修改源验证输入后沿用旧回执。

真实负载manifest和参考RTL testbench由`hw/test`测试侧维护，具体文件位置由用户后续明确。当前`test_bindings.dataset_manifest`、`rtl_testbench`为null、状态pending；不预填目录惯例为真实文件。大payload可由已绑定清单引用可恢复归档，power只保存引用及hash：

| 字段组 | 必需内容 |
| --- | --- |
| 身份 | dataset_id、schema/version、manifest hash、来源种类、采样/生成器版本、受控归档 |
| 来源 | 模型/checkpoint/tokenizer/语料/阶段或实际应用来源；模型派生局部样本须明确；seed、独立片段 ID、样本数量 |
| 设计关联 | export_id、config_id、verification_id；证明这些 payload 已出现在回执 inputs 的 vectors 集合/其受验证清单中 |
| 事务映射 | GEMM/tile/通道、A/B/C/scale 格式/布局/累加/舍入、初始状态、mode_id、每事务 MAC 数 |
| DP 工作量 | target_operand_pairs=target_useful_macs=98304；K-PE/MN-PE组织、完整DUT范围、每DP的K_call、全DUT的C_full、任务K_job、packing/active lane、调用计数、MAC/cycle、II与elapsed cycles分别记录；要求98304%C_full=0且当前模式所选活动资源完整调用 |
| 时间与协议 | 时钟域、握手/气泡/停顿/切换顺序、稳定相位、task_start/task_done 事件定义 |
| 负载文件 | 每个输入、参考输出、事务时序文件及元数据的路径/URI、字节数、hash |
| 验证 | 独立参考语义和精度判据、覆盖矩阵、实际 RTL 结果与周期检查回执 |

仅把某个数据文件放在 test 目录不证明真实来源或被验证。新增 payload/量化/C 策略/事务顺序必须走新的测试数据版本和真实 RTL 回归；power 不自动下载模型、生成输入或刷新 golden。

## 2. DC v1 交接

此表依据 `hw/dc_syn/scripts/report_dc.py` 和 run 结构定义。该 DC 基础设施已通过 PR #4 在 main commit `cf209a9799e65e5c80abdf8a9f5a27289907abc9` 合入，本次只读消费其接口；功耗实施时仍须按正式版本重核字段。接口说明和分支合并不构成真实 EDA 集成验收。

| 当前字段 / 文件 | 消费要求 |
| --- | --- |
| `summary.schema_version` | 接受明确支持的 1；变化需适配，不能猜字段 |
| `run_id / export_id / verification_id` | 与源 run、RTL 门禁和数据清单一致 |
| `status / synthesis_valid` | 正式结果要求 `measured` / true；这仅指该 DC 综合测量 |
| `timing_pass / timing_status` | 正式链要求 true / PASS；保留 setup、hold、未约束检查 |
| `technology / constraints` | 完整复用 profile、PVT、库列表、Vt、周期/IO/门控/层次/线负载；绑定配置 hash |
| `netlist_artifacts` | 当前是 `netlist/文件名 → hash` 字典，不是任意单独网表路径；解析必须在该 run 内并核对 |
| `netlist/<Top>_mapped.v`、`<Top>.sdc`、`<Top>.ddc` | 必须存在、非空、匹配 artifacts；SDF 仅在该综合声明生成时接受 |
| `inputs/resolved.json` | 关联 gate/top、technology、constraints、machine、target_dbs 和原输入指纹 |
| `inputs/hashes.json` / `outputs.sha256.json` | 验证源 RTL、工具、库、模板、约束和最终导出；源产物改动使功耗 stale |
| `power=null`、`power_ready=false`、`netlist_equivalence=not_run` | 保留源记录不改写；功耗验证由新的 power run 独立产出 |

原库 `.db` 及其 hash 必须与本次 PC 使用的一致。功耗基线路线不需要 OpenSTA `.lib`，但必须确认 DB 含所需 internal/leakage/电容模型；门级仿真另需相应标准单元 Verilog。匹配 cell/port 不能单独证明跨 release 的电气一致性。

## 3. power plan 与私有绑定

未来 `PowerPlan` 至少含 `power_run_id`、源 synthesis/export/verification ID、dataset manifest/selector、格式/范围、window profile 与选择、method/version、technology_id、actual period、仿真/SAIF/PC 工具版本和 hash。公开 [flow-plan.json](configs/flow-plan.json) 只声明路由，不填虚假 run ID 或完成状态。

machine 使用 [填写示例](configs/machines/machine.example.json) 的职责；真正的 `machine.local.json` 被忽略。原 DB/工具/setup 引用源 DC machine，标准单元模型和仿真/转换工具在 power machine 显式补充；使用前都要解析成绝对路径/hash。许可证只来自获准外部环境，不进入 JSON、日志摘要或 Git。

## 4. 同源回放与活动回执

| 回执 | 字段与判据 |
| --- | --- |
| `comparison.json` | RTL/gate/golden 来源、仿真器/模型/hash、初始状态、实际周期、事务数、逐模式有效 MAC、数值/握手/延迟/last/idle/stall 判定；标记 workload-specific，不声称形式等价 |
| `window.json` | policy ID/hash、scope、mode/segment/task ID、start/end 原始整数时间、timescale、半开区间、相位/边沿规则、measured_cycles、warmup/初始化区间和排除原因 |
| 数据统计 | unique_source_transactions、repetition_count、来源切片与顺序、accepted/completed、actual simulated period、每事务有效 MAC；重复不作为独立样本 |
| 固定数据对回执 | policy=dp-fixed-macs-v2时，accepted_pairs、completed_pairs、completed_useful_macs均为98304；保存全DUT每次完整调用贡献/ID与整除证据，准备调用独立统计，重试/stall不重复计数，禁止partial tail/padding/取整；完成预算不证明稳态 |
| `activity/audit.json` | gate SAIF/可选 VCD hash、采集方法/转换器/配置、duration/TC/duty、T0/T1/TX/TZ 或版本等价字段、初始值、X/Z、名称映射、annotated/missing 和统计分母 |
| PC 有效活动 | 独立活动计数与实际采用值的比对、关键 clock/ICG/CP/数据检查、逐项例外/边界容差和报告来源；证据不足为 unknown |
| `convergence.json` | candidate_cycles、每次功耗/有效事务数、长度比较/相邻分段差、两个连续通过步、独立片段离散、选择理由或 not_converged；task 用 not_applicable |

回执由实际生产流程写入，不手工填 PASS。数据格式、测试/库/网表或 SAIF 任一变化均重新判断 stale，不凭同名目录复用。

## 5. 功耗及 PPA 关联输出

`PowerResult` 包含 schema/version、run/method/status、源 ID/hash、boundary、included/excluded components、actual PVT/period、窗口和工具版本、各项质量状态、normalized W、原单位、归档和限制。run phase 与结果质量分开：`finished` 只代表执行结束，不等于 verified。

| 数值 | 定义 |
| --- | --- |
| internal_w / switching_w / leakage_w / total_w | 原报告逐项归一，total 为三项和；unknown/null 不能填零 |
| dynamic_w | internal + switching，不能再与 internal/switching 重复求总和 |
| energy_j | total_w × 同窗 duration_s；跨状态/窗口按相应时长积分加权，泄漏不重复加 |
| task_latency_s | 同一 task 窗口声明的开始/完成时间；不能用稳态长度代替任务延迟 |
| useful_macs / energy_per_mac_pj | 有效完成工作量；任务窗为 energy/useful_macs × 1e12，空闲时每 MAC 为 null |
| peak_power_w | 本路线默认 null；短窗口最大平均值另名并记录粒度 |
| uncertainty | 片段离散/收敛与物理模型误差分别存；2% 收敛不等于 2% 硅片准确度 |

功耗结果关联源 DC 的面积、setup/hold、频率和技术 ID，形成新的 PPA 关联记录；不改写 DC 文件。`measured` 按项目约定指有工具证据的测量，必须带 pre-layout/tool-estimate 方法，不能称为硅片实测；`calibrated` 还需要独立留出验证。缺功能、有效活动、窗口或时序证据时保留诊断/未知状态，不发布完整正式 PPA。

K-PE/MN-PE的`fixed_work_burst`保存scope=dot_product、organization、完整DUT范围、原请求表达式`96×1024对数据`、target_operand_pairs=target_useful_macs=98304、实际接受/完成数据对与MAC、C_full和调用数、burst_duration_s、average_burst_power_w、burst_energy_j及energy_per_mac_pj。H16/Q32/E64参考调用数为6144/3072/1536，其他组织按验证过的全DUT容量整除。计数核对后用`burst_energy_j / actual_completed_useful_macs × 1e12`归一；steady_state_status独立保存，未检查为not_assessed。DP组件记录不自动发布为完整阵列/核心profile。
