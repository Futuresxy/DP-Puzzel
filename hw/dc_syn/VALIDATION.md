# 基础设施验证记录

日期：2026-10-24。范围是 DC 自动化软件和项目 skill；没有调用 DC、RTL 仿真、EDA 环境 setup 或功耗工具。

## 软件检查

- Python 3.6.8 与 Python 3.11：`python3 -m unittest discover -s hw/dc_syn/tests -v`，13 项测试通过。新增状态异常场景在一项测试中分别覆盖。
- Shell 语法：`bash -n scripts/dc_syn.sh` 通过；CLI --help 可用。
- Python 编译检查、Tcl info complete 完整性检查、skill-creator quick_validate 与 git diff --check 通过。
- 同时检查实际用户项目目录中的路径和入口；没有在系统 .codex 安装或更新项目 skill。

测试临时构造的 RTL/验证 JSON、库字节和假工具报告只用于软件行为验证，明确标注 fixture，并随临时目录销毁；不是硬件实现、真实 PASS 证据或 PPA 数据。

覆盖：只读 check/prepare、重复 run 拒绝、RTL/testbench/约束变更、准备后和运行期间输入漂移、未记录源/外部 include 拦截、缺精度/周期证据、缺库/非法约束、零进程码但无完成标记、setup/hold 分开判定、多路径组汇总、被舍入掩盖的负 slack、报告缺项 UNKNOWN、未约束警告、错误映射库、DCSH-1、被忽略的约束、输出篡改、清理预览与网表保留、活跃目录/符号链接/路径穿越拒绝、含空格与 Tcl 元字符的路径。

## 真实 EDA 待验收

本项目尚无真实验证回执、综合网表或面积/时序测量。首次验收须由后续授权任务在挂载 EDA 环境选择现有通过 RTL，记录实际工具版本、库/PVT/单位及 hash、全部约束、映射/未约束检查、setup/hold、网表/SDC/DDC 导出及 fingerprint。再独立接入 RTL/netlist 一致性与活动检查，才能把网表用于正式 workload power。

本次只读核对 X-2025.06 官方本地手册，不能据此宣称新 Tcl 全部命令在真实运行中已验证。参考工程历史经验和来源 hash 见 `.skill/dc-synthesis/references/machine-experience.md`（相对仓库根）。
