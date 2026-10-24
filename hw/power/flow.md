# DC + Power Compiler 的负载功耗流程

状态：流程定义，尚无执行实现。授权本流程定义不等于已授权运行仿真/EDA；后续实施/运行任务按当时授权继续，不重复索取已给出的许可。维护入口为本目录文档和根 `.skill/power-analysis/SKILL.md`。

## 1. 工艺、后端与分析边界

使用 DC/Power Compiler，采用标准单元综合后的平均功耗口径，范围为一个阵列或核心。**N22 优先、N12 备选，不自动降级到 OpenSTA 或其他工艺。**公开选择见 [flow-plan.json](configs/flow-plan.json)。

| 角色 | 复用 DC profile | 约束 |
| --- | --- | --- |
| 优先 | `hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json` | N22 BWP7T / 100d，TT 0.9 V、85°C，同一库 release 的功耗 DB 与功能模型 |
| 备选 | `hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json` | N12 BWP6T / 120a Base+LVT，TT 0.7 V、85°C，覆盖两套实际使用单元；保留 DC 的 Vt 分组证据 |

这两个 profile 的当前身份取自工作区 DC v1，使用前检查其版本/hash。库不可读、授权不可用、工况/映射不合格时写明缺项；N12 启用需任务指定，并创建新的对应 DC 与 power run。跨工艺电压/温度/映射的差别不能归因于“节点缩小”一个因素。

功耗会话复用该综合 run 的 DB、operating condition、SDC、周期、输入 transition、输出 load、门控与层次策略，不另行选择 1410 MHz 或全网 100 ps。当前参考 DC 文件的 1410 MHz / 0.10 ns 时钟源 slew 只是显式选择的预算；实际仿真须记录时间精度导致的周期量化。超过已证实时序可达频率的结果不进入正式 PPA。

ZeroWireload / ideal-clock 是第一阶段的已声明假设，没有 CTS/SPEF 或可靠物理毛刺。保留已存在 ICG、触发器内部时钟功耗，不能把未实现的时钟树算成已测。后续加入 SDF/CTS/SPEF 时建立新方法版本，不修改历史记录。

## 2. 一条分析链的步骤

| 阶段 | 输入、动作 | 必需交付 |
| --- | --- | --- |
| 选择 | export、RTL 验证、真实 dataset、synthesis run、窗口策略 | 不含假结果的 plan；明确缺项 |
| 门禁 | 统一 RTL 门禁 + DC 输入/输出 hash + 数据/库匹配 | 每项真实证据；失败不能继续正式功耗 |
| 同源回放 | 原 RTL 与冻结 mapped Verilog 用相同数据、事务、初始状态和时钟 | numerical/protocol 比对、accepted/completed/MAC、初始化与窗口事件 |
| 活动 | 按窗口生成 gate SAIF；直接采集或经核验的 VCD 转换 | scope/timescale/duration/hash，逐信号统计、X/Z/映射检查 |
| PC 会话 | 只读载入同一 mapped Verilog、DB 和 SDC；清除旧活动后注释 SAIF | 注释、missing、单位、功耗和关键功耗计算报告 |
| 窗口验收 | steady-state 做长度/分段检查；task 检查完整事件边界 | convergence / task-completion 证据，不拿稳态替代整任务 |
| 汇总 | 关联 DC 面积/时序与本 run 功耗，检查口径和适用范围 | summary、原始报告索引、输出 hash；独立交给 characterization |

未来公共 runner 分离 `check`（只读输入）、`prepare`（快照计划）、`replay`（已授权仿真）、`analyze`（已授权 PC）、`report`（重新核验并汇总）。这些是**接口职责定义**，当前没有 `scripts/power.sh` 或上述可执行子命令；skill 不得把计划当作现成命令。

## 3. 对接 DC：冻结后只读分析

按 [输入契约](input-contract.md) 解析指定 `hw/dc_syn/runs/<id>/summary.json`、`inputs/resolved.json` / `hashes.json` 和 `outputs.sha256.json`。复核 `synthesis_valid`、`timing_pass`、目标库和输出文件，复用原始 mapped Verilog；不在 power 复制/修改网表。

PC 优先读取**与门级仿真完全同一份 mapped Verilog**，使用匹配 DB 与 SDC 完成 link，确认 top、叶单元和层次。DDC 可作为原始 checkpoint 保留；如以后以 DDC 恢复分析，必须另外证实它与仿真网表的单元/名称/逻辑关系，不凭同名目录假设相同。

DC 原记录中的 `power_ready=false`、`netlist_equivalence=not_run` 是功耗侧尚缺验证的标记，不能直接改成 true。power 自己产出同负载 RTL/gate 比对回执，标记方法为 workload-specific；这不等于所有输入的形式等价。formal 工具后续可补充，但不把尚未进行的证明写成成功。

功耗分析会话不运行 `compile`、重定时、门控插入或 ECO；任何设计变化需新的综合、门级验证和 SAIF。图表与 PPA 汇总通过 ID/hash 联结面积/时序/功耗，**不回写 DC summary 或覆盖其 outputs 清单**。

## 4. 真实负载来自 RTL 测试

数据清单与大 payload 由 `hw/test` 维护，power 只保存数据选择、归档引用及 hash。只有数值格式、布局、scale、C/累加、映射和时间顺序明确且在真实 RTL 测试中验证过的数据能进入正式 workload 功耗。

复用 RTL 测试的事务顺序、valid/ready、气泡、stall、C/scale 更新、参考输出与数值判据；适配器只负责接到冻结门级接口和采集活动。为功耗另建宽松 golden、重排权重或随机填补缺失事务均不允许。源测试只测 II=1 时，只能宣称持续计算微基准，不能自动生成应用级停顿。

数据集必须区分 `captured_model_trace`、`model_derived_local_samples`、`synthetic_validation`。前两者可在声明范围内用于真实数值比较；第三类用于验证/压力对照，不进入真实负载主结果。HiF4 等未确认的项目语义先解决规格，不能借用参考工程编码冒充已定案。

稳定窗需要更长 trace 时，先通过 `hw/test` 的数据流程补充真实片段并重新验证；不能只在 power 悄悄循环。允许的显式 cyclic microbenchmark 单列 repetition_count 和 unique_source_transactions，停止将重复拍数当成独立样本。

## 5. SAIF 与 Power Compiler 接口

优先使用匹配门级模型的仿真器直接采集所选窗口 SAIF；VCS 仅在可用且授权/模型兼容得到验证时作为候选，不假定已可用。备选为零延迟门级 VCD → 已验证转换器 → SAIF，后端仍是 Power Compiler。仿真器和转换器选择写入私有 machine 绑定及 run。

本机 X-2025.06 手册只读核查确认了 `read_saif -input … -instance_name …`、`report_saif -hierarchy`、`report_saif -missing`、`reset_switching_activity`、`report_power` 和 `report_power_calculation`。完整选项在实施时按安装版本核验。本机未找到 `report_switching_activity` 的该版本手册，流程不依赖它。

每个窗口使用独立或彻底清理旧活动的会话；先载入设计/库/原工况并核对单位，再清理旧活动、读取该 SAIF。保存匹配与未匹配对象、名称转换和 annotated/missing 报告。门级同名网表优先精确映射；不以 `auto_map_names` 或忽略整个层次掩盖来源错误。

PC 输出 internal、switching、leakage、total；dynamic=internal+switching。动态与漏电的原始单位可能不同，按报告单位逐项转 W，不能套用 OpenSTA 的“所有结果固定 W”解析经验。归一后核对总和和层次求和；泄漏主要来自映射单元与库/PVT，状态相关模型的概率加权也需记录。

## 6. 活动与功耗验收

- 源文件、库、工具、回执及窗口 hash 一致；实际 PC 授权、工具版本和分析结束证据有效。手册/帮助存在不等于功能获授权。
- 先合法初始化不复位数据路径，使功耗所需引脚状态确定；禁止 force 内部零值或忽略未激活分支 X。初始化/预热是否计入取决于窗口口径，不是统一删除。
- 检查 SAIF scope、duration、timescale、TC 和各状态驻留；区分常量、实际无翻转、无注释和不支持功耗模型。VCD→SAIF 转换保留窗口初始值，核对转换前后统计。
- 建议实际使用且可观测的叶单元功耗引脚覆盖至少 99%，关键时钟/使能/顺序引脚要求完整且例外逐项证明；另保存 PC 自己的统计口径，不把两种分母混用。该阈值是项目计划，不是误差保证。
- 对时钟/ICG、CP、数据/控制热点，将独立 TC/时间和 duty 与 PC 实际采用的活动/关键计算报告核对。精确观测对象优先逐引脚审计；若当前接口无法导出足够证据，标 `effective_activity_audit=unknown`，不能宣称完整验收。
- 保存 slew/load 外推、电气违例和时序状态。不能为通过审计而改 VCD、时钟频率或将全部 CP 强制成 100 ps；继承 DC 假设并单列敏感性。OpenSTA 的历史限幅不推定在 PC 中也存在，但它说明有效活动审计不可省。
- 输出状态同时区分 functional、annotation、effective-activity、timing、window-convergence、power；失败/unknown 的原始报告可用于诊断，不晋升正式 PPA。任务有限 trace 不要求稳态收敛，但必须完成该任务的功能/窗口验证。

源 DC 时序 FAIL/UNKNOWN 时默认不进入正式功耗链；如果后续任务明确要求诊断估计，保留 `diagnostic_only` 并与正式结果分开。无论分析后端为何，都不将未达标频率加入可行 Pareto。

## 7. 输出及当前未执行项

通过 [窗口策略](window-policy.md) 后按 [输出契约](input-contract.md) 保存平均功耗、同窗能量、有效 MAC、task latency、工况、边界和审计状态。稳态、任务和 idle 分开；SAIF 平均结果的瞬时 peak 为 null。`hw/characterization` 发布还需核对适用范围与归档，芯片级组合由 `ratio_dse` 完成。

已知缺项：没有本项目硬件 export/真实回归/综合 run/功耗 runner；当前 PC 相关标准许可查询曾超时，授权未确认；窗口数值尚未实测校准。后续真实验收逐项补证据，不把参考工程的通过记录迁移过来。
