# 单 DP 真实负载功耗

项目采用 VCS 原生门级 SAIF 和 Synopsys Power Compiler。方法与验收项见 [功耗 skill](../../.skill/power-analysis/SKILL.md)。目前处于 DP 架构与实现阶段，已定义测量流程，单 DP 功耗入口和实测结果待后续接入。

| 位置 | 内容 |
| --- | --- |
| `test/data/dp/` | 已提交的 packed 事务、独立期望和数据来源 |
| `hw/rtl/<export-id>/` | 与 DC 匹配的已验证 RTL 快照 |
| `hw/dc_syn/runs/<run-id>/` | 原始 DDC、网表、SDC 和时序结果 |
| `hw/power/runs/` | 实测激励、原生 SAIF、注释审计、工具报告，保留在本机 |
| `hw/power/records/` | 可提交的结果摘要和适用范围 |

同一份通过时序的网表用于各精度重放。选择同源模型数据和固定窗口，逐笔核对 RTL 与门级输出，再检查真实引脚状态、SAIF 时长和 Power Compiler 注释覆盖。整 DP 平均功耗与按有效吞吐折算的 pJ/MAC 一起报告。待测内容、运行范围和工艺条件以明确选定的配置为准。

普通功耗分析按 [统一保留入口](../../scripts/README.md#运行产物保留) 滚动保留最近两次终态运行。功耗运行记录其输入 DC run，重要功耗证据与用户确认后标记保留。

## 下一轮：六种 DP 的固定综合输入

从 [latest_six_dp.json](../dc_syn/records/latest_six_dp.json) 选择六种架构各自最新有效run；查看 [面积与时序表](../dc_syn/records/latest_six_dp.md)。每项已经固定top、1GHz/TT工况、export、原始验证回执及映射Verilog/DDC/SDC校验和，原始文件保留在各自run/netlist/。

当前仅完成综合输入整理，**没有运行功耗测试**。不能把门控寄存器比例或旧vectorless结果当作真实负载功耗。

下一轮执行顺序：

1. 明确每个架构/精度的工作负载和同源数据，固定有效测量窗口。TF32/INT8有匹配真实负载后再加入，不用随机活动替代真实负载结论。
2. 核对冻结RTL与映射网表范围。E96/E128原始快照早于QE优化的共用源码更新；当前还有top/common路径迁移。选择原测量快照重放，或对当前源码重新验证和综合，禁止混用不匹配的RTL活动与旧网表。
3. 完成选定RTL的数值/周期门禁，再以匹配工艺单元模型执行VCS门级数值/协议对比，确认映射网表的功能与L8/II=1。
4. 在排除初始化、填充和排空的负载窗口采集VCS native gate-level SAIF。
5. Power Compiler读取对应DDC/DB/SAIF，完成层次、叶引脚活动、时钟概率/翻转率、注释覆盖和功耗引脚X/Z审计，再记录Internal/Switching/Leakage/Total及pJ/MAC。

当前catalog的power_ready=false、power_mw=null表示这些功耗门禁仍未完成。四份综合修复依赖只用于来源核验，不是第二份功耗网表；功耗应读取对应最终run/netlist/。
