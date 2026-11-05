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
