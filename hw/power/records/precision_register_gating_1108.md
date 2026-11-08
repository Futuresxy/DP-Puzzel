# dp_top 精度寄存器门控：真实负载功耗比较

保持原 T8H16Q32E64 乘法、移位、累加树和 L8/II=1；S1–S3 分段使能及消费端重构。N12 TT/0.7V/85°C，1GHz，VCS native gate-level SAIF + Power Compiler。各格式与原基线采用完全相同的 Qwen3-8B MLP 输入、C、scale 和512ns窗口。

| 格式 | 原动态 mW | 新动态 mW | 动态降低 | 原静态 mW | 新静态 mW | 原总功耗 mW | 新总功耗 mW |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bf16 | 16.392506 | 15.473481 | 5.61% | 0.164434 | 0.199029 | 16.556938 | 15.672550 |
| mxfp8_e4m3 | 16.804265 | 16.413378 | 2.33% | 0.165516 | 0.200999 | 16.969814 | 16.614388 |
| mxfp4_e2m1 | 15.379242 | 12.308616 | 19.97% | 0.163211 | 0.197723 | 15.542459 | 12.506405 |

面积16929.312873→17782.087803µm²（+5.0373%）；寄存器5639→5383，ICG76→148。1GHz setup/hold、VT和电气规则均通过；[综合摘要](../../dc_syn/records/precision_register_gating_1108.md)。

| 格式 | 原关闭时钟引脚/审计总数 | 新关闭时钟引脚/审计总数 |
| --- | ---: | ---: |
| bf16 | 0/5792 | 544/5680 |
| mxfp8_e4m3 | 0/5792 | 264/5680 |
| mxfp4_e2m1 | 0/5792 | 1768/5680 |

关闭引脚为本次负载窗口内实测零翻转；集合包含寄存器及门控相关时钟对象，不等同于关闭寄存器个数。

MXFP4 的8个lane中，寄存器CP逐级统计：S1关闭480/1320、S2关闭696/1504、S3关闭544/1080、S4关闭0/368。按映射实例 ff_sN_sM 名称归属，排除ICG；原始提取结果在新run对应点的lane_clock_gating_summary.json。

每点1024笔负载及合法初始化均经过冻结RTL/VCS门级逐位与L8协议比对。SAIF真实功耗引脚无X/Z，Nets/Ports/Pins全部显式注释；每个叶引脚和时钟引脚活动均与SAIF核对。发布前复核新旧审计引用的文件hash。

- 基线：`hw/power/runs/power_qwen8b_six_1108/`，原DC `dc_dp_top_11080044`。
- 新测量：`hw/power/runs/power_precision_register_gating_1108/`，DC `dc_dp_top_11081432`，快照 `DP_verilog_a32ed7ef4b093ffa`。
- [固定输入计划](../plans/precision_register_gating_1108.json)、[机器摘要](precision_register_gating_1108.json)、[RTL验证](../../../test/results/precision-register-gating.md)。

复现：`python3.11 hw/power/scripts/run_power.py --plan hw/power/plans/precision_register_gating_1108.json --run-id <new-id>`。本次汇总脚本在新run的provenance/report_precision_power.py。

边界：综合后、零延迟、CTS/布线前，无SDF/SPEF，未包含真实布线毛刺；仅本次三个格式/负载实测，不能将MXFP4结果当作NVFP4/HiF4的实测功耗。整体差值包含控制、门控、映射和时序修复共同影响，不是单个RTL改动的独立因果拆分。
