# RTL、数据与功耗产物的位置

本页定义后续实施契约。仓库根记为 `PROJECT_ROOT`；所有持久相对路径以仓库根为基准，run 内相对路径须带明确的 run ID。模板实例化时解析成绝对路径，但不把机器路径写入可提交配置。

## 唯一来源与写入者

| 对象 | 位置 / 写入者 | power 的使用方式 |
| --- | --- | --- |
| Chisel 设计 | `hw/chisel_src/`；硬件实现方 | 只记录源版本，不重新 elaboration |
| 硬件参数 | `hw/configs/`；硬件实现方 | 使用 export 已绑定的参数 |
| 设计 RTL | `hw/rtl/<export-id>/src/<Module>.sv`；统一 exporter | 读 manifest / files.f / hash，不复制或补丁 |
| RTL 验证 | `hw/test/runs/<verification-id>/verification.json`；真实回归入口 | 复用统一门禁，绑定同一 export 和验证输入 |
| 测试源 / 参考 | `hw/test/` 内实际RTL testbench/参考，具体位置待用户绑定；`tb/`、`reference/`为既有目录约定 | 以选定testbench设计门级回放，共用driver/scoreboard，不另造宽松判据 |
| 真实负载数据 | `hw/test/` 内实际数据清单，具体位置待用户绑定；大型payload按测试清单归档 | 只读引用；未绑定时保持pending/null，不填假路径或真实负载标签 |
| 综合证据 | `hw/dc_syn/runs/<synthesis-run-id>/`；DC 入口 | 引用明确 run，复核 summary、inputs、outputs 指纹 |
| 综合网表 | 同一 DC run 的 `netlist/<Top>_mapped.v` | 门级仿真与 PC 共用原文件，不复制进 power |
| DB / SDC / DDC / 可选 SDF | 同一 DC run 绑定的库及 `netlist/` 导出 | DB、SDC 复用原工况；DDC 不是独立的新设计；SDF 必须匹配网表 |
| 标准单元模型 | 已批准的 PDK 原位置；私有 machine 绑定 | 原位读取、记录 release/cell/port/hash；不提交 PDK |
| 功耗策略 / 窗口 | `hw/power/configs/` | 可提交、标记 planned；不得携带假 PASS 或私有路径 |
| 负载选择 / 活动规则 | `hw/power/workloads/`、`activity/` | 元数据契约；不形成第二份 canonical 数据或共享“最新”活动 |
| 完整功耗 run | `hw/power/runs/<power-run-id>/`；未来公共入口 | 独占创建，不覆盖；引用源文件而非复制 RTL/网表 |
| 长期记录 | `hw/power/records/<power-run-id>.json/.csv` | 审查去私有信息后提交，小摘要 + 可恢复归档 URI/hash |
| 发布 profile | `hw/characterization/` | 单独验证后发布；不修改 DC summary 伪造 power-ready |

`workloads/` / `activity/` 存规范与小型选择定义；所有实际 SAIF/VCD 和活动审核结果都属于某个 run。禁止跨 run 共用可写的 `latest.saif`、`latest/netlist` 或裸文件 glob。

## power run 的文件树

以下是待实现产物名，当前只建立目录说明，没有生成下列回执或数据：

```text
hw/power/runs/<power-run-id>/
  README.md                       # 目的、范围、来源、限制和复现命令
  state.json                      # planned/prepared/running/finished/failed/interrupted
  inputs/
    resolved.json                 # export/verification/synthesis/dataset/window/technology ID
    hashes.json                   # 原路径/归档引用/hash；包含库、工具、脚本和模板
    policies/                     # 版本化公开策略快照；不含 RTL/网表/原始数据副本
  scripts/                        # 本次公共模板的快照及 hash，不能作为维护入口
  replay/
    rtl/                          # 同源 RTL 的观测值、计数、日志
    gate/                         # 门级观测值、计数、日志与临时仿真程序
    comparison.json               # 独立 golden 关联 + RTL/gate 数值和协议结论
  windows/<segment-id>/<window-id>/
    window.json                   # start/end、实际周期、scope、来源区间和测量口径
    activity/
      gate.saif                   # 正式分析活动，或可恢复归档
      gate.vcd                    # 需要时保留转换前/诊断活动，不要求每次双份采集
      audit.json                  # 驻留、TC/duty、X/Z、转换、名称和覆盖检查
    pc/
      reports/                    # read_saif、report_saif、units、power 等原始报告
      logs/                       # 工具输出和命令日志
      summary.json                # 本窗口 internal/switching/leakage/total 与质量状态
  convergence.json                # 长度序列、分段结果和选择理由；任务窗可为 not_applicable
  summary.json                    # run 的最终记录；unknown/null 保持未知
  summary.csv
  REPORT.md
  outputs.sha256.json             # 非自引用的完整输出清单
  work/                           # 可重新生成的临时数据库/缓存
```

每个数值模式、数据集、物理工况分别有明确 window/run 身份；同网表的不同格式可在不同功耗 run 引用同一综合 run。不同工艺必须引用各自的综合结果。`outputs.sha256.json` 不散列自身；外部归档替换本地 payload 前记录归档清单、逐文件 hash 及恢复方式。

失败只保留必要错误、配置、输入引用和最小复现，删除不再用于调查的大型生成物前先查下游引用。论文/characterization 已引用的输入不能直接删除；不得清理源 RTL、测试原始数据、源 DC run、PDK 或开发配置。

完整 run 中的私有绝对路径和工具日志留在忽略目录；提交的精简记录用库 ID、相对路径或受控归档 URI 替代。本目录的 `runs/README.md` 是唯一默认跟踪的 run 根文件。
