# 可复用 DC 综合流程

接收 `hw/rtl/<export-id>/` 的已验证 RTL，以明确的工艺库和时序约束综合单阵列/单核心，输出面积、setup/hold 是否通过及功耗所需网表。不复制或修改设计 RTL。

**本次仅搭建自动化基础设施，没有执行 DC、RTL 仿真或生成本项目 PPA 数字。** Python 3.6+，仅标准库。新 Tcl 的真实兼容性、库和许可证连通性仍需在获准的挂载 EDA 环境验收。

完整目录与路径基准见 [paths.md](paths.md)。共享配置分为 configs/technologies（工艺）、configs/machines（本机绑定）和 constraints（时序/综合策略）；模板、驱动、测试和记录分别维护。

## 输入和命令

| 输入 | 位置 |
| --- | --- |
| 原始设计 RTL | `hw/rtl/<export-id>/src/`，由 manifest.json / files.f 精确列举 |
| RTL 验证证据 | `hw/test/runs/<verification-id>/verification.json` |
| 工艺/PVT | `configs/technologies/n22-tt-0p9v-85c.json` 或 `n12-base-lvt-tt-0p7v-85c.json` |
| 时序和综合策略 | 显式 constraints JSON；历史预算起点 `constraints/reference-1410mhz.json` |
| 本机工具/库绑定 | `configs/machines/machine.local.json`，Git 忽略；无默认私有路径 |

单个新 RTL 文件也要先进入合法 export，并完成 SV testbench 精度和周期验证。本入口不生成 RTL/testbench，不提供跳过验证选项。统一门禁为 [rtl_gate.py](../../scripts/rtl_gate.py)，未来 power 可复用。字段见 [输入契约](input-contract.md)。

从仓库根目录操作：

```bash
cp hw/dc_syn/configs/machines/machine.example.json hw/dc_syn/configs/machines/machine.local.json
# 编辑本机文件，绑定真实可读的 DB、可执行 dc_shell 和已批准的环境入口。
export_id='REPLACE_WITH_PASSED_EXPORT_ID'
technology='hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json'
constraints='hw/dc_syn/constraints/reference-1410mhz.json'
machine='hw/dc_syn/configs/machines/machine.local.json'
bash scripts/dc_syn.sh check --export-id "$export_id" \
  --technology "$technology" --constraints "$constraints" --machine "$machine"
bash scripts/dc_syn.sh prepare --export-id "$export_id" \
  --technology "$technology" --constraints "$constraints" --machine "$machine" --run-id my-run
```

check 只读，不创建 run；prepare 校验相同输入并写快照/launch.sh，不启动 DC、不生成测量值。两者都要求实际 DB 和工具文件可读，不能在缺库时声称预检查通过。工艺和约束均无隐式默认选择。

只有当前任务已授权实际综合且已接入挂载 EDA 时执行：

```bash
bash scripts/dc_syn.sh run --run-id my-run
# 或 bash hw/dc_syn/runs/my-run/launch.sh
bash scripts/dc_syn.sh report --run-id my-run
```

运行前后核验所有输入 hash 和统一 RTL 门禁。更改 RTL、验证输入、库、约束或脚本后重新 prepare 新 run，不修改快照继续执行。自动 run ID 含 top、UTC 微秒时间和输入指纹；自选 ID 也不能复用。启动加载本机环境入口，不复制、打印或提交许可证环境变量。

## 输出和判定

```text
hw/dc_syn/runs/<run-id>/            # 完整目录默认不提交
  inputs/                         # DC Tcl、解析后 JSON/Tcl、报告模板和全部输入 hash
  state.json                      # prepared → running → finished/failed/interrupted
  logs/                           # stdout、stderr、命令日志
  reports/                        # 官方面积、QoR、setup、hold、约束和完整性报告
  netlist/<Top>_mapped.v           # 功耗/一致性检查输入，不是另一份设计 RTL
  netlist/<Top>.sdc                # 最终约束
  netlist/<Top>.ddc                # DC checkpoint，默认保留
  netlist/<Top>.sdf                # 仅 write_sdf=true 生成
  summary.json                    # 权威机器记录，未知值为 null
  summary.csv                     # 单条扁平面积/时序记录
  REPORT.md                       # 按 templates/report.md.in 渲染
  outputs.sha256.json              # 报告、网表、日志和摘要指纹
  work/                           # 可删除的 WORK/alib/临时数据库
```

`synthesis_valid` 与 `timing_pass` 分开；退出码：0=证据完整且 setup/hold PASS；2=输入/工具/证据无效；3=有效综合但时序 FAIL；4=有效综合但时序 UNKNOWN。违例 run 保留真实面积和负 slack，不宣称达到目标频率。

有效综合要求进程返回 0、完成标记、指定库映射、全部必要报告和非空网表/SDC/DDC。最终叶单元必须全部解析到目标库，未映射/GTECH/未知 blackbox 拒绝。时序同时检查全设计 QoR 的 WNS/TNS/违例数与高精度路径 slack，缺项为 UNKNOWN。check_timing 显式检查无时钟、无 IO 约束、部分 IO 约束、未约束 endpoint、组合环等；警告阻止 PASS。忽略约束/不支持选项和工具错误阻止有效结果。

面积来自官方 report_area，工具版本来自实际 QoR。ZeroWireload 下是标准单元综合面积，单位由 profile 明确为 µm²；不含布线、CTS 和提取寄生。

## 配置范围

v1 支持一个时钟、统一 IO 预算、完整映射到标准单元库的设计。复位与其他非时钟输入计时，不自动 false-path；IO min/max 分开，单位显式 ns/pF。参考 1410 MHz 文件采用 **min IO=0、clock gating=false、preserve_hierarchy=true**，是待审查起点，与旧项目默认策略不同，不能直接当作严格同条件对比。

N12 支持 base+LVT 会话 Vt 分组与 20% hard 上限，保留实际 cell usage / Vt 报告。面积恢复调用 optimize_netlist -area，避免请求 X-2025.06 已知可能被忽略的 area_high_effort_script。hold 修复后同时报告 setup/hold。clock gating 为显式选择，使用前核验工艺单元和活动仿真链。

多时钟、异步复位例外、自定义 false/multicycle path、参数覆盖、宏/blackbox、UPF、physical/topographical 模式未接入；扩展时更新契约和验收。新工艺必须核验库/PVT、面积单位和单位换算，不能只按文件名判断兼容。

## 功耗衔接、清理和记录

power 读取明确 run 的 summary、netlist、解析配置、库 hash 和源 export。`netlist_equivalence=not_run`、`power_ready=false` 表示仍需单独证明 RTL/netlist 一致性并校验 VCD/SAIF 层次、窗口和覆盖率；本入口不生成冒充 workload power 的 vectorless 数字。

```bash
bash scripts/dc_syn.sh clean --run-id my-run         # 只列计划和字节数
bash scripts/dc_syn.sh clean --run-id my-run --apply # 仅删除 work/
```

只接受 finished/failed run，拒绝活跃、中断、穿越路径和符号链接。保留全部 inputs/reports/logs/摘要、mapped Verilog、SDC、DDC 和可选 SDF。失败 run 同样保留错误日志、参数和来源。不提供删除网表/整份 run 的自动入口；缩减 DDC/SDF 前核对下游引用并建立可校验归档。

运行数据记录在每份 run 的 summary JSON/CSV，当前没有测量记录。长期小型摘要策略见 [records/README.md](records/README.md)；来源与经验见 [skill 参考](../../.skill/dc-synthesis/references/machine-experience.md)。

## 验证

```bash
python3 -m unittest discover -s hw/dc_syn/tests -v
bash -n scripts/dc_syn.sh
```

测试在临时目录使用明确标注的假工具/报告，只验证软件流程、门禁、解析和清理，不运行 DC/硬件仿真。首次真实验收需选择已有通过的 RTL，核对命令支持、库/PVT/单位、完整约束、setup/hold 和网表，再补真实验收记录。本次不触发该验收。
