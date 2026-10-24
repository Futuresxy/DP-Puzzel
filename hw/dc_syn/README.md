# DC 综合：面积、时序和层级查看

输入为已通过 SV 回归的 `hw/rtl/<export-id>/`，输出到 **`runs/dc_<RTL顶层名>_<月日时分>/`**，例如 `dc_Bf16SignPipe_10241850`。时间采用 Asia/Shanghai（UTC+08），同顶层同分钟不覆盖。完整路径见 [paths.md](paths.md)，输入字段见 [input-contract.md](input-contract.md)。Python 3.6+，仅标准库。

默认启用 **clock gating**，保留模块层级和 PE 子树。实际面积/时序以同工艺、约束、门控和展开策略的工具报告为准；没有执行仿真或 DC 时不生成测量值。

## 使用

本机 DB/工具/环境路径填写到被忽略的 `configs/machines/machine.local.json`；模板为同目录 machine.example.json。不存密码或许可证配置。

```bash
export_id='实际已通过的导出ID'
technology='hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json'
constraints='hw/dc_syn/constraints/reference-1410mhz.json'
machine='hw/dc_syn/configs/machines/machine.local.json'
bash scripts/dc_syn.sh check --export-id "$export_id" \
  --technology "$technology" --constraints "$constraints" --machine "$machine"
bash scripts/dc_syn.sh prepare --export-id "$export_id" \
  --technology "$technology" --constraints "$constraints" --machine "$machine" \
  --purpose '比较 PE 模块的面积与时序'
# prepare 打印本次 run 名称，例如 dc_MyTop_10241850。
bash scripts/dc_syn.sh run --run-id dc_MyTop_10241850
bash scripts/dc_syn.sh report --run-id dc_MyTop_10241850
```

check 只读；prepare 写输入快照但不启动 DC；run 只在任务已授权且挂载 EDA 可用时执行。自定义 --run-id 必须采用同样格式且 top 匹配。RTL 只读、不复制到 DC。整个 RTL 目录只有一个指纹，关联真实回归与综合；其余文件只保留路径/版本，不逐文件写 hash 清单。

## 层级与 clock gating

默认约束配置的关键项为：

```json
"clock_gating": true,
"clock_gating_min_bitwidth": 4,
"hierarchy": {
  "keep_modules": ["PE*", "Pe*", "pe_*", "SubPE*", "ProcessingElement*"],
  "expand_modules": [],
  "expand_instances": [],
  "expand_depth": 0
}
```

expand_depth=1 选择顶层下一层，=2 再包含第二层；expand_modules 按模块 reference pattern 选择，例如 Core*；expand_instances 按完整实例路径选择，例如 core0/input_buffer。keep_modules 匹配的 PE 及其内部层级优先保留。若要展开这些模块，先明确调整保护列表。

流程只移除选中边界，不递归 ungroup -flatten；其余层级通过 no_autoungroup/no_boundary_optimization 保留，模块内部仍正常优化。选择记录在 reports/hierarchy.tsv，面积分解在 area_hierarchy.rpt，实际引用在 reference.rpt，门控结果在 clock_gating.rpt。父模块的 inclusive 面积包含子模块，不能重复相加。展开“维度”是层级深度、模块和实例选择，不修改 RTL 中阵列尺寸或硬件实例数量。

clock_gating 可显式设 false；修改门控或层级策略后使用新 run。跨策略面积对比应注明差异，功耗沿用对应 run 的网表和层级，并单独验证活动匹配。

## 产物与判定

```text
runs/dc_<Top>_<MMDDHHMM>/
  inputs/        # 解析后配置、DC/hierarchy Tcl、报告模板
  reports/       # 面积、setup/hold、QoR、层级、门控和约束报告
  netlist/       # <Top>_mapped.v、<Top>.sdc、<Top>.ddc，可选 SDF
  logs/          # stdout、stderr、命令日志
  summary.json   # 时间/目的/工艺/源码/综合结果
  summary.csv
  REPORT.md
  state.json
  work/          # 可清理的工作库、alib 和临时数据库
```

不生成 inputs/hashes.json 或 outputs.sha256.json。`records/` 只保留[核心数据](records/README.md)，用 `report --record <文件名.json>` 更新。实际配置快照在 inputs，原始工具输出在 reports/logs。

退出码：0=综合证据完整且 setup/hold PASS；2=输入/工具/证据无效；3=有效综合但时序 FAIL；4=时序 UNKNOWN。完成标记、有效映射、必要报告和非空网表均须齐全；缺项不补零，负 slack 不放宽为 PASS。面积来自官方 report_area，ZeroWireload 不代表布局布线后面积。

```bash
bash scripts/dc_syn.sh clean --run-id dc_MyTop_10241850
bash scripts/dc_syn.sh clean --run-id dc_MyTop_10241850 --apply
```

清理只删除终态 run 的 work；报告、网表、SDC/DDC 和回归证据保留。功耗前仍需独立完成 RTL/netlist 一致性、时序和活动覆盖检查。当前支持单时钟/统一 IO/N12-N22 标准单元库；多时钟、UPF、宏单元和自定义时序例外仍待接入。

DC 不包含 testbench、精度验证入口或 tests 目录；只消费 hw/test 已通过的 RTL。项目软件回归为 `python3 -m unittest discover -s hw/test/unit -v`；例子的导出/验证也在 hw/test，综合只通过 scripts/dc_syn.sh 执行。见 [BF16 示例](examples/bf16_sign_pipe/README.md)。本 PR 只保留最新工作流和一套最新例子产物。
