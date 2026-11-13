# dp_top v1.8：1 GHz 电气规则修复

本次仅对已验证 v1.8 基线的映射网表进行 DC 增量电气修复，未修改 RTL、流水、数值合同或时钟约束。新 run 为 `dc_dp_top_11092301`，输入为 `dc_dp_top_11091816` 的 DDC；两次运行及其报告均保留。

| 项目 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 总单元面积 / µm² | 16163.057770 | 16165.122154 |
| 组合面积 / µm² | 12482.850991 | 12484.915375 |
| 时序面积 / µm² | 3680.206779 | 3680.206779 |
| 最差 setup slack / ns | 0.000001311 | 0.000001311 |
| 最差 hold slack / ns | 0.000393212 | 0.001306176 |
| max capacitance 违例 | 1 | 0 |
| setup / hold / 电气 / VT 门禁 | 未全部通过 | 全部通过 |

面积增加 2.064384 µm²（约 0.0128%）。使用 `compile -incremental_mapping -only_design_rule` 修复 `u_global_alignment/n1117` 负载问题，未指定手工单元替换，未编辑综合网表。`max_leakage_power=0` 为功耗优化目标，报告中的该目标违例不属于电气规则；最大电容、转换时间和扇出规则均已检查。

工况保持 TSMC CLN12FFCLL、120a、6T base/LVT、TT/0.7V/85°C、1 GHz、setup uncertainty 0.1 ns、ICG 开启。DC X-2025.06；LVT 占非黑盒单元 13.01%，低于 20% 上限。完整技术标识、约束和各级时序见[精简 JSON](dp_top_v18_electrical_repair_20261109.json)。最紧路径仍为 S4 lane SOP 到 S5 group compare_exp，setup 裕量极小；这是综合后结果，不能代替布线后或多角签核。

输入快照为 `DP_verilog_d7c8c865ebf856be`，K_FP16=16、LOCAL_W=28、GLOBAL_W=40，L8/II=1；原冻结验证回执 `test/runs/verilog/20261109T101330231426Z/verification.json` 保留。新功耗分析必须使用本次修复网表并重新进行冻结 RTL/门级负载重放，不能沿用旧网表的 SAIF。

复现：

```sh
python3.11 hw/dc_syn/scripts/run_dc.py prepare \
  --export-id DP_verilog_d7c8c865ebf856be \
  --technology hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json \
  --constraints hw/dc_syn/constraints/dp-mixed-1000mhz-incremental.json \
  --machine hw/dc_syn/configs/machines/machine.local.json \
  --run-id dc_dp_top_<new_timestamp> \
  --purpose 'v1.8 baseline electrical repair' \
  --design-rule-repair-from dc_dp_top_11091816
PYTHON=python3.11 bash scripts/dc_syn.sh run --run-id dc_dp_top_<new_timestamp>
```

完整网表、DDC、SDC、日志和报告保存在本地 `hw/dc_syn/runs/dc_dp_top_11092301/`。本结果及依赖作为本轮六架构比较证据保留，旧结果不删除。
