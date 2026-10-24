# Power Compiler 流程定义检查

日期：2026-10-24。范围是目录、计划配置、数据契约和项目 skill；没有编写功耗 runner/仿真 TB/PC Tcl，没有运行仿真、综合、功耗分析或新的许可查询，也没有生成 PPA 数值。

## 本次检查

- `skill-creator/scripts/quick_validate.py .skill/power-analysis` 通过。
- 本目录 Markdown 链接/锚点、表格、UTF-8/LF、JSON 解析、配置引用、N22 优先/N12 显式切换、长度倍增与收敛参数的一致性检查通过。
- `git diff --check`、待提交文件大小、私有路径/凭据和 ignore 规则检查通过；仅跟踪 `runs/README.md`，实际 run 和 machine.local.json 仍被忽略。
- 开工时存在的独立 DC 工作按文件 SHA-256 保留；本次只在 skill 索引追加功耗说明，不纳入其已有 DC 索引改动或其他 DC 文件。

这些检查只说明定义与当前工作区接口自洽，不证明 EDA 命令或功耗数值已验收。未来 runner 的软件测试、标准单元/SAIF 兼容性、实际许可、窗口收敛及真实 PPA 验收都尚未进行。

## K-PE/MN-PE固定数据对预算v2

按用户最新决定，K-PE/MN-PE多周期DP微基准改用`96×1024 = 98304`对有效标量A/B数据，即98304 MAC、196608 OP。当前默认指向dp-fixed-macs-v2，原v1保持原字节作为历史planned配置。H16/Q32/E64每次完整调用16/32/64对，目标调用数6144/3072/1536。

检查16/32/48/64/96/128容量的调用数6144/3072/2048/1536/1024/768及最小公倍数384，均精确整除98304。实际K-PE/MN-PE profile仍须按全DUT的C_full逐项核验，不据算术示例宣称所有profile已验证。v2禁止尾块、padding和取整；初始化/预热与计数窗口分开，固定数据量不等于固定周期或稳态。

具体数据及参考RTL testbench路径留在hw/test待用户后续明确，当前绑定为pending/null。已定义参考该testbench复用激励/协议/scoreboard、接入DC网表和单元模型生成门级SAIF的方法。本次仅检查配置/文档/skill，不生成数据或testbench，不运行仿真/EDA，不认定活动已稳定。

## DC 接口快照

以下快照记录初次流程定义时的独立 DC 基础设施；它们已通过 PR #4 在 main commit `cf209a9799e65e5c80abdf8a9f5a27289907abc9` 合入。追加 MAC 定义时核对原30份DC相关文件与main字节一致，在隔离checkout中保留两项skill索引并合入main；本次没有修改DC实现或运行其EDA流程。源字段变化后仍需复核功耗消费者。

| 文件 | SHA-256 |
| --- | --- |
| `hw/dc_syn/scripts/run_dc.py` | `c92d2eaaa2f7279e9edaa7cbc2bac2e099e4794e56a418bd18e5992372c8a721` |
| `hw/dc_syn/scripts/report_dc.py` | `ad0cd12cc694eff979826e74a5057ffe80972c5bf9d3071563c8fdb8a4429794` |
| `hw/dc_syn/templates/DC.tcl` | `ceff5c512718fdec3f390af68f0de54dcccdc25af72590144e014b2eb6ae2aba` |
| `hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json` | `3b1f4b4be5aa9ef9f9a9d5f9689c480c70fbecb0520480eb6cb971409e2492b7` |
| `hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json` | `cc7c6446cfdcbed05dbd64ce8f83d8d160429dcf2386a43eedea1453ab4b49db` |

## 本地官方接口来源

只读检查已安装 X-2025.06 命令手册；下面路径相对该 DC 安装根，公开记录不包含机器私有根路径或手册原文：

| 来源 | SHA-256 |
| --- | --- |
| `doc/syn/man/cat2/read_saif.2` | `fce05410cfab366281cc3e27929c806a86a1f05afcc1febde8ceb3d0796cde97` |
| `doc/syn/man/cat2/report_saif.2` | `99328df4f70121699d71d9f45c7e843e134e9f192ddcc2ca60fc79e12cdce418` |
| `doc/syn/man/cat2/reset_switching_activity.2` | `6230100f0684fc5dfdfad066d8330ca7a816a72fd0d412cb1dd43c5b92f9b1e3` |
| `doc/syn/man/cat2/report_power.2` | `7a703df81611b7c51f129fa685fb909046d7ca36e7d2091c8d9b3f3e3893f678` |
| `doc/syn/man/cat2/report_power_calculation.2` | `f4311e149d655ac7d6351593b8b1d550d3e67a9f655b6c32875f12893f4695f7` |

窗口方法的外部来源与工程阈值的区别见 [window-policy.md](window-policy.md)。此前只读环境核查的许可超时仍未解决；不根据安装组件或手册存在声称已获可用授权。
