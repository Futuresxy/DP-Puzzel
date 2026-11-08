# Q32E64 精度寄存器门控：真实负载功耗比较

在既有 dp_lane_qe 内调整 S1–S3 寄存使能和字段恢复，保留算术、group接口、L8/II=1。N12 TT/0.7V/85°C，1GHz，VCS native gate-level SAIF + Power Compiler；各格式与原基线使用相同 Qwen3-8B MLP 输入、C、scale 及512ns窗口。

| 格式 | 原动态 mW | 新动态 mW | 动态降低 | 原静态 mW | 新静态 mW | 原总功耗 mW | 新总功耗 mW |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mxfp8_e4m3 | 13.886584 | 13.638106 | 1.79% | 0.136239 | 0.135929 | 14.022802 | 13.773998 |
| mxfp4_e2m1 | 12.699382 | 10.894652 | 14.21% | 0.134606 | 0.133563 | 12.833946 | 11.028178 |

面积 11542.081582→11873.120309 µm²（+2.8681%）；1GHz setup/hold、VT和电气规则通过。[综合摘要](../../dc_syn/records/qe_precision_register_gating_1108.md)。

| 格式 | 原关闭时钟引脚/总数 | 新关闭时钟引脚/总数 |
| --- | ---: | ---: |
| mxfp8_e4m3 | 0/4648 | 264/4744 |
| mxfp4_e2m1 | 0/4648 | 1104/4744 |

MXFP4 的8个QE lane中，按映射寄存器CP归属：S1关闭320/1072、S2关闭208/1016、S3关闭544/1072、S4关闭0/352。E4M3仅S2关闭256/1016，其他阶段未关闭。统计排除ICG，本次逐级数据和复现脚本保存在run内。

关闭引脚来自窗口内实测零翻转；包含寄存器和门控相关时钟对象，不等于关闭寄存器个数。所有点均重跑冻结 RTL 和 VCS 门级仿真：1024笔负载及独立合法初始化通过逐位与L8检查。SAIF真实功耗引脚无X/Z，Nets/Ports/Pins全部显式注释，逐叶引脚活动审计通过。发布前复核新旧审计引用的文件hash。

- 基线：`hw/power/runs/power_qwen8b_six_1108`，DC `dc_dp_top_q32e64_11080855`。
- 新测量：`hw/power/runs/power_qe_precision_register_gating_1108`，DC `dc_dp_top_q32e64_11081629`，快照 `DP_verilog_q32e64_8fc17d1108154f48`。
- [固定计划](../plans/qe_precision_register_gating_1108.json)、[机器摘要](qe_precision_register_gating_1108.json)、[功能验证](../../../test/results/qe-precision-register-gating.md)。

复现：`python3.11 hw/power/scripts/run_power.py --plan hw/power/plans/qe_precision_register_gating_1108.json --run-id <new-id>`。本次汇总脚本在新run的provenance/report_qe_power.py。

范围：只实测独立 Q32E64 的 E4M3/MXFP4。混合顶层共享 QE 源码且已功能回归，但本次未重测其面积/功耗；NVFP4/HiF4也不能套用MXFP4测量值。功耗为综合后零延迟、CTS/布线前，无SDF/SPEF，不包含真实布线毛刺；整体差值包含门控、字段恢复和综合映射的共同影响。
