---
name: dc-synthesis
description: Prepare, run, inspect, and maintain DP-Puzzel Design Compiler synthesis for verified RTL exports, with explicit technology and timing constraints, area and setup/hold reports, power netlist handoff, and scoped cleanup.
---

# DC 综合自动化

在 DP-Puzzel 处理新 RTL 的 DC 综合、N12/N22 切换、面积/时序报告或综合产物维护时使用。硬件边界为单阵列/单核心；实际 EDA 依当前任务授权和挂载环境可用性执行。

先读根 AGENTS.md、[流程入口](../../hw/dc_syn/README.md)。环境排查和历史经验读 [machine-experience.md](references/machine-experience.md)；接入 export/验证生产器读 [输入契约](../../hw/dc_syn/input-contract.md)。命令从仓库根执行。

## 新 RTL / 新综合任务

1. 明确 export ID、top、工艺/PVT、周期、IO min/max/transition/load 和层次策略，优先已有配置。1410 MHz 文件只是历史预算起点，不自动选工艺或约束。
2. 用公共 `scripts/rtl_gate.py EXPORT_ID` 检查同一份 RTL 的 SV testbench 精度与周期证据。新单文件也走 export manifest/files.f。缺证据或 hash 失效时停止 PPA，报告需实际回归；不手写 PASS、不直接综合裸 sv。
3. 在忽略的 `hw/dc_syn/configs/machines/machine.local.json` 绑定库与工具绝对路径，逐库核对 ID/PVT/hash。N12 base+LVT 必须同角；不改 PDK，不提交私有路径/许可证。
4. 调用 check，再 prepare，均不启动 DC。需要实际执行且当前任务已授权、已接入挂载 EDA 时调用 run；已有授权不重复询问。仅准备流程的任务保留未执行状态。

```bash
bash scripts/dc_syn.sh check --export-id "$export_id" \
  --technology "$technology_json" --constraints "$constraints_json" --machine "$machine_json"
bash scripts/dc_syn.sh prepare --export-id "$export_id" \
  --technology "$technology_json" --constraints "$constraints_json" --machine "$machine_json" --run-id "$run_id"
# 仅在已授权且挂载 EDA 可运行时：
bash scripts/dc_syn.sh run --run-id "$run_id"
bash scripts/dc_syn.sh report --run-id "$run_id"
```

唯一 runner 为 hw/dc_syn/scripts/run_dc.py，DC 模板为 hw/dc_syn/templates/DC.tcl。维护公共脚本，不新增绑定 top/日期/私有路径的一次性脚本。输入变化创建新 run，不编辑快照继续启动。

需要最小真实验收且已获任务授权时，使用 [BF16 示例](../../hw/dc_syn/examples/bf16_sign_pipe/README.md) 的 scripts/dc_example.py run。它先执行独立参考 + SV testbench，再由统一 gate 放行 DC；模板逐字节导出，来源明确为 systemverilog，不虚构 Chisel 类。PDK 的 Key has expired 先报告挂载凭据问题，只有用户授权并提供认证方式后刷新 kinit；不把密码写入脚本/配置。

## 判定与交付

- 综合完成、面积有效、setup/hold 通过分别判断。退出 0 才是完整证据下 timing PASS；2 无效、3 有效测量但 timing FAIL、4 UNKNOWN。不能用进程返回 0、COMPLETE 或非零面积替代时序验收。
- 读明确 run 的 summary.json 和原始 area/qor/timing_setup/timing_hold/check_timing。缺项不补零；微小负 slack 仍失败。全设计 QoR 覆盖所有路径组，detail 复核舍入。
- Vt 上限、hold 修复、clock gating、层次策略影响 PPA，比较时须一致。X-2025.06 不依赖 design area attribute，不请求已知可能忽略的面积高强度选项；面积恢复看 optimize_netlist 和官方报告。
- 交付 netlist 下 mapped.v/SDC/DDC、可选 SDF、库指纹及 export/verification/run ID。power_ready=false 保持到独立完成一致性与活动检查；不把 DC vectorless 功耗当 workload 功耗。
- 数据在 run 的 summary JSON/CSV 与 REPORT.md。长期摘要按 hw/dc_syn/records/README.md 去私有路径并关联可核验归档后提交。未经实际运行，不能声称当前库/许可证可用或该 Tcl 已通过本项目真实 DC。

## 清理与维护

先 `bash scripts/dc_syn.sh clean --run-id "$run_id"` 看计划，任务已授权清理时加 --apply，只删终态 run 的 work/。保留网表、约束、证据、报告和日志，不自动删 DDC/SDF、整份 run 或下游引用物。活跃/中断状态或符号链接被拒绝时调查进程与路径，不绕过保护。

修改后运行 `python3 -m unittest discover -s hw/dc_syn/tests -v`、`bash -n scripts/dc_syn.sh` 和 Tcl 完整性检查。假工具测试只证明软件行为，不能宣称 EDA 兼容或硬件验证通过。新工艺、多时钟、宏/blackbox、UPF、时序例外先更新契约及验收。
