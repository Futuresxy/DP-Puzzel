# dp_top 精度寄存器门控综合

N12 BWP6T16P96CPD 120a base+LVT，TT/0.7V/85°C；DC X-2025.06；K16/LOCAL28/GLOBAL40，L8/II=1，1GHz，ICG开启。同原基线的 `dp-mixed-1000mhz-incremental.json` 最终约束，无新增 false/multicycle path、case analysis 或 retiming。

| 指标 | 原基线 | 精度门控 |
| --- | ---: | ---: |
| 总面积 µm² | 16929.312873 | 17782.087803 |
| 组合面积 µm² | 13132.136627 | 14102.286526 |
| 时序单元面积 µm² | 3797.176246 | 3679.801277 |
| 寄存器数量 | 5639 | 5383 |
| ICG 数量 | 76 | 148 |
| 门控寄存器数量 | 5563 | 5307 |
| setup/hold/VT/电气规则 | PASS | PASS |

面积增加5.0373%，包含新增控制/重构及本次技术映射、时序修复的整体代价，不能把全部差额归因于ICG本体。新结果最差setup/hold slack分别为0.041246ps/0.172973ps，LVT占18.52%；余量很小，限于指定TT角的预布局综合。

- 原基线：`hw/dc_syn/runs/dc_dp_top_11080044`。
- 新结果：[dc_dp_top_11081432](../runs/dc_dp_top_11081432/REPORT.md)，快照 `DP_verilog_a32ed7ef4b093ffa`。
- 功能回执与补充测试：[精度门控验证](../../../test/results/precision-register-gating.md)。综合准备引用063108完整回归，之后对相同快照加强补充测试并完成063933完整回归；两份原始回执均保留。
- [机器摘要](precision_register_gating_1108.json)；完整网表/DDC/报告只保存在本机run。

门控覆盖率不等于实际关闭比例，真实负载活动及功耗由独立SAIF审计确定。
