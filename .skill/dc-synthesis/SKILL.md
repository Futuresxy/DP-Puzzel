---
name: dc-synthesis
description: Run evidence-gated single-DP Design Compiler synthesis and inspect stage timing with explicit technology and constraints.
---

# DP Design Compiler 综合

入口为 `scripts/dc_syn.sh`，实际运行遵从当前用户授权；本机绑定只写忽略的 `hw/dc_syn/configs/machines/machine.local.json`。先读根 AGENTS.md、`hw/dc_syn/README.md` 和 `hw/dc_syn/input-contract.md`。

1. 记录分支、实际基线、top、参数、容量、L/II。DP 主实现为纯 Verilog；不混入同名 SystemVerilog 模块，不固定功能输入。
2. 构建固定依赖 CModel，运行 `python3 test/run_verilog.py --implementation verilog --phase all`。只能消费该次通过的 `hw/rtl/DP_verilog_<fingerprint>/`，运行 `python3 scripts/rtl_gate.py EXPORT_ID`。不手改 `ppa_eligible`、PASS 或回执。
3. 读取已有工艺 profile 和机器绑定，运行 `python3 hw/dc_syn/scripts/check_environment.py --technology TECHNOLOGY --machine MACHINE`，核验真实许可证及精确 DB。库版本/PVT不符不能替换；原始工具/库日志私有保存。
4. `bash scripts/dc_syn.sh check ...` → `prepare ...` → 已授权时 `run --run-id ...` → `report --run-id ...`。check/prepare 不启动 DC。输入变化建立新 run。
5. 默认门控开启、保持层级、保留 DP 子树；显式传入参数和 Verilog language，时钟与同步 reset 正常计时。不可通过 false path/multicycle/case analysis 隐藏违例。
6. 同时检查 link、未映射叶、check_design/check_timing、setup/hold、单位、库、门控、网表/SDC/DDC。退出码 0=完整且时序与 Vt 配额通过，2=无效，3=有效但时序或 Vt 配额失败，4=未知。
   若只剩 hold 违例，可在新 run 使用 `prepare --hold-repair-from SOURCE_RUN`；门禁/配置必须一致，临时增加 1 ps 修复裕量后恢复原始约束，复查全部报告。
7. DP 每级报告 `timing_S1.rpt` 至 `timing_S8.rpt`，以 `register_stages.tsv` 复核寄存归属；检查 unclassified 和输出边界。读 startpoint/endpoint 及路径逻辑，不仅看 WNS。
8. 首先保留基线测量，再提出等价组合优化或流水重新分配；每个改动版本重新 RTL 回归和综合。任何架构改变同步 spec、CModel、TB；不能从估算声称时序通过。

结果限于指定库/PVT/预算下的综合，不代表布线或多 corner 签核。功耗须另有活动与一致性证据；`power_ready=false`。records 只存精简结果与来源，PDK、私有路径、许可证不提交。

日常综合结果按 [运行产物保留](../../scripts/README.md#运行产物保留) 轮转。需要作为长期基线、重要节点或论文证据的 run 先与用户确认，再标记保留。

软件维护后运行 `python3 -m unittest discover -s hw/dc_syn/tests -v` 和 `bash -n scripts/dc_syn.sh`。fixture 不能作为硬件或 EDA 通过证据。流程通用部分来源于本仓库 `be850fc04659c42ce65badde75557bae1776aa69`，此次接入新版 DP 合同；历史经验见 `references/machine-experience.md`，不继承旧 BF16 测量。
