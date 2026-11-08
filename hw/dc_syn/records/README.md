# 当前六种 DP 综合结果

统一入口：[最新面积与时序表](latest_six_dp.md)，机器可读数据：[latest_six_dp.json](latest_six_dp.json)。这里仅保留这份六架构汇总和本说明；每类原始报告在对应最终run的REPORT.md及reports/中。

六种架构为dp_top、T8H16Q32E96、T8H16Q32E128、优化T8H16Q64E128、E64、Q32E64。统一N12 TT/0.7V/85°C、1GHz、L8/II=1、LOCAL28/GLOBAL40、ICG开启。汇总核对原始报告、冻结RTL、原始数值回执、输入/输出校验及必要修复依赖，明确属于历史已测证据，不伪造当前源码的新门禁。

复核命令：`python3.11 hw/dc_syn/scripts/latest_synthesis.py --write`。只复核/发布，不启动EDA、不删除文件。新的综合完成后，按每种架构选择最新全部验收通过的run；不以较晚的失败实验替代有效结果。

## 本地目录与功耗输入

runs根目录只保留六份最终结果。每份保留映射Verilog、DDC、SDC、报告、配置和日志；四份结果的原始修复来源位于各自provenance/repair_sources/，带完整文件hash索引。run_dc.py的repair_run_path/verify_repair_source支持这些不可变来源，拒绝缺失、歧义或被修改的内容。

latest_six_dp.json固定后续功耗所需top/export/验证回执以及网表/DDC/SDC的路径和SHA-256；不含私有PDK路径或许可证。尚无门级等价、SAIF和注释覆盖结果，因此power_ready=false、power_mw=null。具体待办见 [功耗准备](../../power/README.md)。

## 历史记录

用户于2026-11-08要求只保留六种架构最新综合结果及报告，覆盖此前对已删除旧run的保留约定。旧对比/诊断报告已从records移除，精简报告仍可从本地Git提交 `a368630` 读取，例如：

```bash
git show a368630:hw/dc_syn/records/mixed_n12_1000mhz_20261108.md
git show a368630:hw/dc_syn/records/qe_area_opt_n12_1000mhz_20261108.md
git show a368630:hw/dc_syn/records/dp_n12_timing_20261105.md
```

这说明历史数值的原始语境，不能把旧报告作为当前RTL的新验收。清理清单见 [维护回执](../maintenance/latest_six_cleanup_20261108.json)：保留六份最终run、四份必要修复来源；删除十二份旧run，并用本汇总代替十八份旧记录。已删除原始网表/大产物不在Git中；Git只可恢复旧精简报告。未清理hw/rtl、test/runs或测试数据。
