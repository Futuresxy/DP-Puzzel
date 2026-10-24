# DC 路径约定

PROJECT_ROOT 从脚本位置解析；不依赖 shell 当前目录或“最新文件”。CLI 相对配置路径按调用目录解析，推荐从仓库根执行。

| 对象 | 唯一位置 |
| --- | --- |
| 设计 RTL、清单和目录指纹 | `hw/rtl/<export-id>/`，DC 只读 |
| 真实 SV 回归证据 | `hw/test/runs/<verification-id>/verification.json` |
| 工艺/PVT | `hw/dc_syn/configs/technologies/*.json` |
| 本机绑定 | `hw/dc_syn/configs/machines/machine.local.json`，忽略 |
| 时序、门控及层级策略 | `hw/dc_syn/constraints/*.json` |
| 模板 | `hw/dc_syn/templates/DC.tcl`、hierarchy.tcl、report.md.in |
| 运行目录 | `hw/dc_syn/runs/dc_<RTL-top>_<MMDDHHMM>/` |
| 解析配置与实际脚本 | `<run>/inputs/` |
| 官方面积、setup/hold、约束、门控报告 | `<run>/reports/` |
| PE/模块面积 | `<run>/reports/area_hierarchy.rpt` |
| 层级展开计划与 reference | `<run>/reports/hierarchy.tsv`、reference.rpt |
| 功耗所需 mapped Verilog / SDC / DDC | `<run>/netlist/<Top>_mapped.v`、`<Top>.sdc`、`<Top>.ddc` |
| 工具日志 | `<run>/logs/` |
| 运行摘要 | `<run>/summary.json`、summary.csv、REPORT.md |
| 可删除工作库与缓存 | `<run>/work/` |
| 可提交核心结果 | `hw/dc_syn/records/*.json` |

示例名称为 `dc_Bf16SignPipe_10241850`：10 月 24 日 18:50。目录名不加年份、秒或指纹，同分钟冲突不覆盖；完整时间留在摘要里。

唯一指纹在 RTL manifest 中，回归和综合引用同一值。不再生成 inputs/hashes.json 或 outputs.sha256.json。功耗流程按 run 路径、目录指纹和固定 netlist 文件名衔接，独立核对一致性、时序和活动覆盖。

clean 默认预览，仅删除 finished/failed run 的 work，保留源码、网表、约束、报告和验证证据；拒绝活跃/中断 run、符号链接和穿越路径。不创建公共 latest、netlist 或 reports 别名。
