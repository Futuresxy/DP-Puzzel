# DC 综合：面积、时序和层级查看

输入为已通过 RTL 回归的 `hw/rtl/<export-id>/`，输出到 **`runs/dc_<RTL顶层名>_<月日时分>/`**，例如 `dc_dp_top_11050024`。时间采用 Asia/Shanghai（UTC+08），同顶层同分钟不覆盖。完整路径见 [paths.md](paths.md)，输入字段见 [input-contract.md](input-contract.md)。通用入口使用标准库；新版 DP 回归/门禁要求 Python 3.9+。

默认启用 **clock gating**，保留模块层级和 PE 子树。实际面积/时序以同工艺、约束、门控和展开策略的工具报告为准；没有执行仿真或 DC 时不生成测量值。

## 使用

本机 DB/工具/环境路径填写到被忽略的 `configs/machines/machine.local.json`；模板为同目录 machine.example.json。不存密码或许可证配置。

```bash
export_id='实际已通过的导出ID'
technology='hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json'
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

`dc_syn.sh clean` 针对单次终态 run 的 `work/`。普通终态 run 的整体轮转使用 [统一保留入口](../../scripts/README.md#运行产物保留)，最近两次普通综合保留，已被结果记录或其他分析引用的 run 独立保护。重要综合证据经用户确认后标记保留。功耗前仍需独立完成 RTL/netlist 一致性、时序和活动覆盖检查。当前支持单时钟/统一 IO/N12-N22 标准单元库；多时钟、UPF、宏单元和自定义时序例外仍待接入。

DC 消费根 `test/runs/` 的真实验证证据。流程和门禁软件测试运行 `python3 -m unittest discover -s hw/dc_syn/tests -v`。DP 数值与周期回归在根 `test/`，综合入口为 `scripts/dc_syn.sh`。

## 单 DP / N12 / 1.41 GHz 与 1 GHz

实际 RTL 基线为 `138c4b1d2be2e9e626387db67461ed113e56c77a`，工作分支
`chore/dp-dc-12nm`。通用 runner/templates 从本仓库提交
`be850fc04659c42ce65badde75557bae1776aa69` 移植，未包含原目录未提交修改。

```sh
# 先按 src/cmodel/README.md 构建；Python >= 3.9，Verilator timing 需支持 coroutine 的 C++ 编译器
python3 test/run_verilog.py --implementation verilog --phase all
python3 scripts/rtl_gate.py DP_verilog_3fa3420882896719
python3 hw/dc_syn/scripts/check_environment.py \
  --technology hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json \
  --machine hw/dc_syn/configs/machines/machine.local.json
bash scripts/dc_syn.sh check --export-id DP_verilog_3fa3420882896719 \
  --technology hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json \
  --constraints hw/dc_syn/constraints/dp-1410mhz.json \
  --machine hw/dc_syn/configs/machines/machine.local.json
# 使用同一组显式选项 prepare，再按打印的 run ID 执行 run/report。
```

上述 export ID 对应已通过门禁的 v1.5.1 28/40 功能回归。修改设计后使用新回归返回的 ID。历史综合记录对应 27/40。
N12 profile 为项目既有 TT 0.7 V / 85°C 分析角，非最差工况或多 corner 签核。
约束继承项目预算：0.709219858 ns 周期、0.10 ns setup uncertainty、0.03 ns hold
uncertainty、0.20/0 ns IO max/min、0.10 ns 输入 transition、0.01 pF 输出负载。
没有 datatype/valid case analysis，没有 false/multicycle path；同步 reset 计时。

DP 增加每级捕获寄存器报告与输出边界报告。`register_stages.tsv` 用于复核归属，
`timing_S*.rpt` 用于定位级内最差链。门控和未分类寄存器不得静默丢弃；
全局 timing/QoR 仍是验收依据。缺少 PPA 项时保持 null/unknown。

本机复现工具组合：Python 3.11、CMake 3.28.4、Boost 1.83.0、nlohmann_json 3.11.3、
CModel GCC 8.5.0、Verilator 5.030、仿真器编译 GCC 10.3.1。
若 Verilator 安装时未配置 coroutine 编译选项，在选择 GCC 10+ 的 PATH 后，使用
`CXXFLAGS='-std=c++20 -fcoroutines'`；本次还设置 `CCACHE_DISABLE=1`，避免写系统缓存。
这些选项只影响测试仿真器构建。TB 缓冲区为 2048 行，覆盖当前最大 1053 行 campaign；
超出容量会拒绝，不丢弃用例。真实使用的依赖 archive 校验和在 `dependencies/cmodel.json`。


本次 [流水时序分析与边界](records/README.md#历史记录) 包含各级路径、通过/失败端点及优化建议。
已完成 run 可用 `python3 hw/dc_syn/scripts/inspect_dc.py --run-id RUN_ID` 只读载入 DDC 补报；
该入口不优化、不改网表，只有全局关键路径与原报告完全复现才接受分级结果。
`report` 会更新派生摘要；setup/hold 和 LVT 配额分别报告，flow_pass 要求全部满足。


`dp-1000mhz.json` 仅将周期改为 1 ns。1GHz 首轮 setup 通过，但残留一条 −0.266 ps hold 违例；
独立修复 run `dc_dp_top_11050215` 的 setup/hold 与 Vt 配额均通过，最差 slack 分别为 +0.003815 ps / +1.100987 ps。
可在相同 `prepare` 选项上增加 `--hold-repair-from SOURCE_RUN`，在新 run 内载入有效源 DDC 只做 hold 优化；
门禁、库、机器绑定和最终约束必须相同。优化时临时增加 1 ps hold uncertainty，报告/SDC 恢复原值，
并重新检查 setup/hold 与 Vt；不会把修复成功作为前提。源 run 保留，不覆盖原始失败证据。

## E64 与多精度同工况比较

E64 顶层为 dp_top_e，选择 `python3 test/run_verilog.py --frontend e --phase all`，门禁接受 `DP_verilog_e_<fingerprint>`。多精度顶层仍为 dp_top，使用默认回归。两者分别核对源清单、数值/协议、断点与回执，见 [输入合同](input-contract.md) 和 [E64 RTL 报告](../../test/results/e64-v1.5.8.md)。

本批用户明确授权 E64 综合，并要求验证、DC 及比较基线作为重要结果长期保留。使用相同 N12 TT 0.7V/85°C、K16/28/40、L8/II1、dp-1000mhz.json、门控、层级和 Vt 预算，分别综合当前 E-only 和多精度设计；历史 27/40 数据只作背景，不能混入同参数面积百分比。[正式结果与路径](records/README.md#历史记录)统一追踪两类测量。

DC 在 compile/optimize_netlist 后可能使此前缓存的 collection 失效。hold 修复前及修复编译后按稳定的 clock_port 名重新获取时钟；不复用过期的 `_sel...` 句柄，不更改时钟或 uncertainty。首轮若出现 CMD-036/UID-95，门禁判为无效，在新 run 重跑并保留原始诊断；不能引用该 run 的面积冒充有效测量。

### 时序优先复测

`constraints/dp-1000mhz-timing-first.json` 保持原1GHz时序、IO、门控、层级和工艺预算，只设置 `optimize_area=false`，跳过 `set_max_area 0` 与显式 `optimize_netlist -area`；仍保留工具正常映射、设计规则和 hold 修复。用该文件替换 check/prepare 的 `--constraints`，在新 run 中执行。它不保证所有设计时序必然通过，最终仍检查 setup/hold 和 Vt。

E64 同一已验证快照的实测 run dc_dp_top_e_11052354 已全部通过，面积增加2.54%；[对齐逻辑核验和时序结果](records/README.md#历史记录)记录小数点转换、逐级核对及各级余量。与面积优先结果比较时须注明策略不同，不能覆盖旧报告或放宽负 slack 判据。

## 混合 DP / 1GHz

三个混合 profile 使用 `test/run_mixed_verilog.py` 产生各自验证回执。与当前 `dp_top` 比较时统一使用 `constraints/dp-mixed-1000mhz-incremental.json`，开启门控、关闭显式面积恢复、最多两次增量时序优化，仅展开 DFF 包装层。数值/流水源代码不变，不使用 retiming。

若有效映射仍有小量 setup 违例，可在新的 run 中 `prepare --timing-repair-from <source-run>`；输入必须与有效源完全一致，临时加严50ps后恢复原始最终约束。若仅有hold违例，可使用已有 `--hold-repair-from`。不接受错误工具运行或缺失证据的DDC作为修复源。原始网表/DDC/报告留在本地 runs，精简比较记录放 records。

四顶层同工况的报告生成命令及结果入口见 [比较记录](records/README.md)。DC 流程软件测试为 `python3.11 -m unittest discover -s hw/dc_syn/tests`；软件测试不替代真实综合。

若 setup/hold 已通过但有 max_capacitance/max_transition/max_fanout 违例，使用 `prepare --design-rule-repair-from <source-run>` 先做设计规则修复，再修复 hold。该入口允许跟随一次 setup/hold 修复，但会逐级验证祖先运行完整性和输入一致性，不允许重复电气修复链。最终三类电气违例也纳入 flow_pass；泄漏优化产生的 Required=0 不作为已承诺的用户功耗预算。

电气自动修复仍未解决的反相器负载可显式传入 `--resize-inverter <instance> <expected-ref> <target-ref>`，只允许用于电气修复。DC 校验当前实例引用、base 库两端口结构和输出函数一致后执行 size_cell，并保护该尺寸避免重新缩小。源 DDC、实例和两个引用名写入运行输入/精简记录，随后仍完整检查 setup/hold/电气规则/VT；不得用它替换不同逻辑或手改网表。

## 当前六架构结果入口

查看 [最新面积/时序汇总](records/latest_six_dp.md) 和 [功耗输入catalog](records/latest_six_dp.json)。runs根目录只保留每种架构最新有效结果，修复来源保存在其provenance/repair_sources/并校验hash。历史记录的清理与Git回看方法见 [records说明](records/README.md)。

## 同功能寄存器驱动修复

已定位到映射后寄存器驱动瓶颈时，可在新的 `--design-rule-repair-from <run>` 中显式传入 `--resize-register <instance> <expected_ref> <target_ref>`。仅允许同一 DFQD 家族/VT 的驱动增强；DC核对实际源实例、顺序单元属性、CP/D/Q端口与输出函数，执行 `size_cell` 并保存来源，不手改网表、不增加流水。所选库模型的功能体等价检查放在该run的provenance。随后必须重新检查setup/hold、VT、电气规则和门级结果，诊断候选的正slack不能代替正式验收。
