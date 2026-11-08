# 单 DP 真实负载功耗

项目采用 VCS 原生门级 SAIF 和 Synopsys Power Compiler。方法与验收项见 [功耗 skill](../../.skill/power-analysis/SKILL.md)。已完成Qwen3-8B真实MLP数据和首批固定计划；单DP的仿真/测量执行器和实测结果待接入。具体程序分工、门禁和窗口见 [搭建方案](implementation-plan.md)，首批为BF16、MXFP8 E4M3、MXFP4 E2M1。

| 位置 | 内容 |
| --- | --- |
| `test/data/dp/` | 已提交的 packed 事务、独立期望和数据来源 |
| `test/data/power/` | 本轮 Qwen3-8B 原生 K 功耗负载及两套数值参考 |
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

## Qwen3-8B 首批准备

[已导入数据](../../test/results/qwen3-8b-power-data.md)覆盖7种格式和当前所需K，共15套、每套1024笔；与旧correct_961分目录保存。冻结选择见 [15点计划](plans/qwen3_8b_first3.json)：先运行dp_top的三个精度，再扩展到其余兼容顶层。当前只有只读准备入口可执行：

```bash
python3.11 hw/power/scripts/prepare_qwen_plan.py --output hw/power/plans/qwen3_8b_first3.json
```

它检查数据/网表/DDC/SDC校验和并固定选择，不启动EDA，不替代统一RTL门禁或门级验证。完整执行器按 [implementation-plan.md](implementation-plan.md) 接入后，先生成VCS原生SAIF，再做Power Compiler测量。
