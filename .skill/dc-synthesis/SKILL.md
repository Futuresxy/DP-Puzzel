---
name: dc-synthesis
description: Prepare, run, inspect, and maintain DP-Puzzel Design Compiler synthesis for verified RTL exports, with explicit technology and timing constraints, area and setup/hold reports, power netlist handoff, and scoped cleanup.
---

# DC 综合自动化

在 DP-Puzzel 处理新 RTL 的 DC 综合、N12/N22 切换、面积/时序报告或综合产物维护时使用。硬件边界为单阵列/单核心；实际 EDA 依当前任务授权和挂载环境可用性执行。

先读根 AGENTS.md、[流程入口](../../hw/dc_syn/README.md)。环境排查和历史经验读 [machine-experience.md](references/machine-experience.md)；接入 export/验证生产器读 [输入契约](../../hw/dc_syn/input-contract.md)。命令从仓库根执行。

## 新 RTL / 新综合任务

1. 明确 export ID、top、工艺/PVT、周期、IO min/max/transition/load 和层次策略，优先已有配置。1410 MHz 文件只是历史预算起点，不自动选工艺或约束。
2. 用公共 `scripts/rtl_gate.py EXPORT_ID` 检查同一份 RTL 的 SV testbench 精度与周期证据。新单文件也走 export manifest/files.f。缺证据或 RTL 目录指纹不一致时停止 PPA，报告需实际回归；不手写 PASS、不直接综合裸 sv。
3. 在忽略的 `hw/dc_syn/configs/machines/machine.local.json` 绑定库与工具绝对路径，核对 ID/PVT、版本和可读性。只有 RTL 目录保留一个整体指纹；不再为工具、库、报告或网表列单文件指纹。N12 base+LVT 必须同角，不改 PDK、不提交私有路径/许可证。
4. 调用 check，再 prepare，均不启动 DC。需要实际执行且当前任务已授权、已接入挂载 EDA 时调用 run；已有授权不重复询问。仅准备流程的任务保留未执行状态。

```bash
bash scripts/dc_syn.sh check --export-id "$export_id" \
  --technology "$technology_json" --constraints "$constraints_json" --machine "$machine_json"
bash scripts/dc_syn.sh prepare --export-id "$export_id" \
  --technology "$technology_json" --constraints "$constraints_json" --machine "$machine_json" --purpose '本次综合目的'
# 仅在已授权且挂载 EDA 可运行时：
bash scripts/dc_syn.sh run --run-id "$run_id"
bash scripts/dc_syn.sh report --run-id "$run_id"
```

唯一 runner 为 hw/dc_syn/scripts/run_dc.py，DC 模板为 hw/dc_syn/templates/DC.tcl。维护公共脚本，不新增绑定 top/日期/私有路径的一次性脚本。输入变化创建新 run，不编辑快照继续启动。

run 名固定 dc_<RTL-top>_<MMDDHHMM>，采用 Asia/Shanghai 时间，同分钟重名拒绝覆盖。默认 clock_gating=true、展开深度 0、保留 PE 子树。用 hierarchy.expand_depth、expand_modules、expand_instances 自定义层级展开；keep_modules 优先保护 PE 及内部层级。不得为方便面积或功耗分析而完全平铺设计；查看 area_hierarchy.rpt、hierarchy.tsv 和实际网表层级。

DC 不生成或运行 testbench，只消费 hw/test 的真实通过回执；唯一综合入口为 scripts/dc_syn.sh。需要 BF16 最小例子时，先在 hw/test/scripts/bf16_sign_pipe.py 分别 export、verify，再按 [示例说明](../../hw/dc_syn/examples/bf16_sign_pipe/README.md) 调用 DC。测试配置、参考和软件回归都在 hw/test。只维护当前工作流，不在 PR 保留旧例子 run 或历史对比副本。PDK 的 Key has expired 先报告，用户授权后才刷新 kinit，不存密码。

## 判定与交付

- 综合完成、面积有效、setup/hold 通过分别判断。退出 0 才是完整证据下 timing PASS；2 无效、3 有效测量但 timing FAIL、4 UNKNOWN。不能用进程返回 0、COMPLETE 或非零面积替代时序验收。
- 读明确 run 的 summary.json 和原始 area/qor/timing_setup/timing_hold/check_timing。缺项不补零；微小负 slack 仍失败。全设计 QoR 覆盖所有路径组，detail 复核舍入。
- Vt 上限、hold 修复、clock gating、层次策略影响 PPA，比较时须一致。X-2025.06 不依赖 design area attribute，不请求已知可能忽略的面积高强度选项；面积恢复看 optimize_netlist 和官方报告。
- 交付对应 run 的 mapped.v/SDC/DDC、可选 SDF、库/PVT/版本和源 RTL 目录指纹。power_ready=false 保持到独立完成一致性与活动检查，不把 DC vectorless 功耗当 workload 功耗。
- summary JSON/CSV 和 REPORT.md 保留核心结果，完整配置在 inputs，原始输出在 reports/logs。用 report --record <文件名.json> 生成精简记录，仅记录目的、时间、工艺、源码路径、频率/工具/门控和面积时序。不重建逐文件 hash 清单，不把旧无门控结果改标成有门控。

## 清理与维护

先 `bash scripts/dc_syn.sh clean --run-id "$run_id"` 看计划，任务已授权清理时加 --apply，只删终态 run 的 work/。保留网表、约束、证据、报告和日志，不自动删 DDC/SDF、整份 run 或下游引用物。活跃/中断状态或符号链接被拒绝时调查进程与路径，不绕过保护。

修改后运行 `python3 -m unittest discover -s hw/test/unit -v`、`bash -n scripts/dc_syn.sh` 和 Tcl 完整性检查。假工具测试只证明软件行为，不能宣称 EDA 兼容或硬件验证通过。新工艺、多时钟、宏/blackbox、UPF、时序例外先更新契约及验收。
