# 本机参考经验与来源

2026-10-24 阅读 Quant_LLM_Chip_Codesign/HW/dc_syn 及 DC skill 后整理。参考 checkout HEAD：`0ddc5f7c21082dbce73d992a4d33a5a331f1e0bc`；此版本用于定位参考经验。

参考文件包括 DC.tcl、scripts/run_dc.py、scripts/report_dc.py、CURRENT_CONFIG.md、ARTIFACTS.md、DC skill、multi-Vt 约束和 VALIDATION.md。保留参考版本和文件名，不为每份参考文件列指纹。

只迁移通用经验，未改参考工程、复制其 RTL/网表/报告/私有环境，未把旧面积当本项目结果。新入口不依赖参考 checkout 存在。

## 环境与库

- 参考记录在可连许可证的主机上使用 DC X-2025.06；沙箱中 DCSH-1 曾对应许可证连接失败。这是历史定位，当前同类错误仍需区分环境入口、网络、授权和许可证；不反复启动、不修改许可证配置。
- 主挂载与备用镜像目录层次不同：前者为 `主挂载/install/<release>/...`，后者为 `备用挂载/<release>/...`。不能只替换前缀，须核验真实可读路径、发布版本和 DB basename。均不可读时停止，不换 PVT 顶替。
- N22：BWP7T30P140/100d，TT 0.9 V/85°C；N12：BWP6T16P96CPD/120a base+LVT，TT 0.7 V/85°C。profile 只保留库标识，本机位置在忽略的 local 配置。
- 某些库不含 threshold_voltage_group；参考流程在会话中标 base/lvt，再设 20% hard LVT 数量上限和 leakage optimization。必须查真实 leaf usage/Vt 报告，不能从 target_library 推断实际比例。

## 综合与验收

- 返回 0 不等于跑到 exports；因此同时检查完成标记、报告、导出及指纹，新流程还核验运行前后的输入。
- X-2025.06 曾以 OPT-1341 忽略 area_high_effort_script；新流程直接采用 compile_ultra、显式 optimize_netlist -area 和设计规则修复，失败不静默降级。
- current_design 的 area/total_power attribute 在历史环境不可靠；以官方面积报告为准。
- setup/hold 独立处理，降频不能修复短路径 hold；hold 修复后重新报告两者。默认两位小数可能隐藏负 slack，新流程用 9 位精度并复核 detail。
- 多路径组不能只取第一组。缺全设计 QoR 汇总或 detail 时保留 UNKNOWN。
- ZeroWireload 不含实际布线、CTS/SPEF；工艺/PVT/IO/门控/Vt/hold/层次策略不同不能作为严格同条件比较。

## 与旧工程的区别

设计 RTL 唯一位置为 hw/rtl/export-id，不复制到 dc_syn/rtl_src。旧 UNTESTED 归档不能升级 PASS。1410 MHz 参考约束显式采用 min IO=0、clock gating=true、默认保留层级/PE 子树，暴露 hold 预算与层次选择供审查，并非原 PETile 默认配置等价拷贝。

旧工程精简后只留四份报告不适用本项目；power 需要真实 netlist/SDC，长期证据还需 hold 和完整约束检查。默认仅删 work，不删 mapped.v/DDC/SDC/SDF；没有活动测量就不生成 workload power。

## 本次验证边界

只读核对本机 X-2025.06 官方命令手册：安装目录 doc/syn/man 下 dc_shell、check_timing、set_units、report_qor、report_constraint、set_svf，确认相关启动选项、ns/pF、QoR 精度与检查列表。手册/Tcl 完整性核对不等于真实 EDA 兼容验收。

上述来源整理阶段只做软件回归与静态检查，未运行 DC、仿真或 PPA。后续同日用户单独授权 Bf16SignPipe 最小例子的真实回归/DC，已形成 [本项目验收记录](../../../hw/dc_syn/records/bf16_sign_pipe_smoke_20261024.json)，不是移用参考项目的历史通过记录。

该验收实际遇到 NFS PDK 的 Key has expired；用户授权 kinit 后恢复可读，随后按相同 N22 profile 和 1410 MHz 约束完成综合。保留真实来源，不在脚本存 Kerberos 密码。当前例子报告包含层级保留的 OPT-133、DesignWare 自动加入库的 UISN-40 和命名规则的 UCN-4 提示；check_timing 无警告，最终 leaf 全部解析到 N22 target。此通过证据只覆盖例子与该工况，其他格式/设计/工艺仍需逐配置验证。

当前 run 名采用 dc_<Top>_<MMDDHHMM>；唯一指纹只覆盖 RTL 目录，回执/库/工具/报告/网表不逐文件散列。按深度、模块和实例选择展开，保护 PE 子树；最新实际门控结果和简洁 records 见例子记录。
