# 路径与保留契约

`PROJECT_ROOT` 由脚本自身位置解析，当前用户工作目录为 DP-Puzzel；代码不写死机器路径。不把当前 shell 工作目录或“最新文件”作为输入。相对配置文件 CLI 参数按调用目录解析，推荐从仓库根调用；输入契约内的路径按下表解析。

| 对象 | 唯一位置 | 路径基准 / 写入者 |
| --- | --- | --- |
| 设计 RTL | `PROJECT_ROOT/hw/rtl/<export-id>/src/` | exporter；DC 只读，不复制 |
| RTL 清单与来源 | 同一 export 下 manifest.json、files.f、README.md | files.f 相对 export；DC 只读 |
| 验证回执 | `PROJECT_ROOT/hw/test/runs/<verification-id>/verification.json` | 回执引用和输入路径相对 PROJECT_ROOT；真实回归入口写 |
| 工艺/PVT profile | `hw/dc_syn/configs/technologies/<technology>.json` | 可提交，只有 ID/PVT/策略，无库私有路径 |
| 本机工具和库绑定 | `hw/dc_syn/configs/machines/machine.local.json` | 忽略；工具/DB/setup 必须是明确绝对路径，不存密钥 |
| 时序与综合策略 | `hw/dc_syn/constraints/<constraint-id>.json` | 可提交；最终生效值快照到 run |
| 综合模板 | `hw/dc_syn/templates/DC.tcl` | 可提交；每次 prepare 复制并校验 hash |
| 报告模板 | `hw/dc_syn/templates/report.md.in` | 可提交；prepare 快照，run 渲染 |
| run 根 | `hw/dc_syn/runs/<run-id>/` | runner 独占创建，不覆盖既有目录，完整目录忽略 |
| 全部输入指纹 | `<run>/inputs/hashes.json` | 绑定源 RTL、验证输入/日志、配置、库、工具和自动化代码 |
| 官方原始报告 | `<run>/reports/` | DC 写 area/qor/setup/hold/check_timing 等报告 |
| 功耗网表 | `<run>/netlist/<Top>_mapped.v` | DC 写；不可手改、不可当成设计 RTL |
| 约束 / checkpoint | `<run>/netlist/<Top>.sdc`、`.ddc` | 默认生成和保留；SDF 显式选配 |
| 日志 | `<run>/logs/` | stdout/stderr/命令日志，失败也保留 |
| 运行机器记录 | `<run>/summary.json`、summary.csv、REPORT.md | runner 写；含实际指标、版本、状态和来源 |
| 全部输出指纹 | `<run>/outputs.sha256.json` | 绑定报告、日志、网表及摘要，report 复核 |
| 可删除中间物 | `<run>/work/` | WORK、alib、临时编译数据库；clean 默认仅预览 |
| 长期小型记录 | `hw/dc_syn/records/<run-id>.json/.csv` | 人工审查/去私有路径并关联归档后显式提交，不自动发布 |

不创建跨 run 的公共 netlist/、reports/ 或 latest/，避免功耗引用错版本。功耗入口从指定 synthesis run 的 summary 和网表指纹解析输入，保留 export/verification/run 三个 ID；独立执行 RTL/netlist 一致性和活动检查。

清理仅删除 finished/failed run 内的 work；不会删 RTL、报告、日志、网表、SDC/DDC/SDF 或 records。活跃或中断状态、符号链接、目录穿越一律拒绝。若后续需要迁移大产物，先建立归档 URI/hash 与下游引用记录，再设计单独的归档流程。
