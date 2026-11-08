# 当前六种 DP 综合结果

统一入口：[面积与时序](latest_six_dp.md)、[机器索引](latest_six_dp.json)。五种复用架构为精度寄存器门控版，E64沿用原专用E设计；均为N12 TT/0.7V/85°C、1GHz、L8/II=1、LOCAL28/GLOBAL40、ICG开启。

runs中保留六份当前最终结果及旧功耗对照依赖的五份历史DC基线；必要修复祖先收在最终run的provenance/repair_sources，带完整文件hash索引。全部现用及功耗对照的网表/DDC/SDC、工具配置、报告、冻结快照和回归证据保留。

功耗以独立的[六架构报告](../../power/records/current_six_precision_gated.md)为准。catalog中的power_ready=false与power_mw=null属于综合流程占位；具体负载已通过门级重放、SAIF与注释审计，证据由功耗报告绑定。

复核：`python3.11 hw/dc_syn/scripts/latest_synthesis.py --write`。只发布通过全部验收的综合结果，不启动EDA。当前源码与冻结输入分别核验，不能用旧报告替代新源码验证。

本轮[清理回执](../maintenance/precision_gated_six_cleanup_20261108.json)记录无引用测试/快照的清理及保留依赖；已退役快照只保留manifest/README等失效说明。全部旧功耗对照数据和现存DC比较摘要继续保留。此前清理的记录见[历史维护回执](../maintenance/latest_six_cleanup_20261108.json)；已删除的大产物不能从Git恢复。
