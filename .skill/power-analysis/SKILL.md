---
name: power-analysis
description: Define and audit DP-Puzzel workload power flows using verified RTL-test data, gate simulation, SAIF, and DC/Power Compiler. Use for power plans, windows, N22/N12 selection, activity evidence, and DC area/timing handoff; this project workflow currently has no executable power runner.
---

# DP-Puzzel Power Compiler 功耗分析

遵循根 AGENTS.md；支持单DP组件微基准及单阵列/单核心，DP记录不能冒充完整array/core profile。用户已选择 **真实 RTL 测试负载 → 门级仿真 → SAIF → Power Compiler**，N22 优先、N12 显式备选。不要自动换 OpenSTA、其他工艺或另一套输入数据。

先读 [power 入口](../../hw/power/README.md) 和 [流程](../../hw/power/flow.md)。核对数据/综合输入时读 [输入契约](../../hw/power/input-contract.md)，窗口选择/长度问题读 [窗口策略](../../hw/power/window-policy.md)，维护产物时读 [路径契约](../../hw/power/paths.md)。按当前任务需要读取，不将历史 PETile 的路径、采样数、编码和通过结果当成本项目默认事实。

## 当前能力与任务授权

目前只有流程、目录和 planned 配置，没有功耗 runner、SAIF 采集 TB 或 PC Tcl。定义/更新 skill 的任务只维护这些资产，不自动实现硬件、生成 RTL、采样模型、运行仿真或 EDA。后续实施任务可建立维护入口并验证；运行任务已有授权且环境满足时继续，不反复询问。缺实现或输入时具体报告，不发明 `power.sh` 命令或手工 PASS。

实际运行仍需获准的本机挂载 EDA。当前已发现 X-2025.06 功耗接口，但标准许可查询曾超时，不能声称 PC 可用；在实际环境核验所需授权，不修改许可证、PDK 或用户配置解决问题。

## 输入选择与 DC 交接

1. 明确 export、verification、synthesis run、dataset/segment/task、format/mode、dot_product/array/core的完整DUT范围和窗口类型。设计RTL只读`hw/rtl/<export-id>/src/`，按manifest/files.f和统一`scripts/rtl_gate.py`验证，不复制设计RTL。
2. 读取明确 DC run 的 summary、resolved、input/output hash 和原 `netlist/<Top>_mapped.v` / SDC / DB。正式链要求 `synthesis_valid=true`、`timing_pass=true`；库、PVT、周期/IO/门控/层次一致。DC 的 power-ready/equivalence 尚未运行标记保持不变，由 power 独立提供同负载比对，不冒充形式等价。
3. 默认选择 [N22 计划](../../hw/power/configs/flow-plan.json) 指向的 DC profile；N12 需任务明确选择和新的匹配综合 run，Base/LVT 模型覆盖全部实际单元。缺 N22 依赖时报告缺项，不静默 fallback；不复制工艺库或提交私有路径。
4. 数据及参考RTL testbench归`hw/test`，具体路径由用户后续明确，当前`test_bindings`保持pending/null，不预填假文件。绑定后只引用已验证的输入/golden/事务时序清单及hash；参考该testbench复用driver、激励、时钟/握手、scoreboard与完成事件，接入DC网表和匹配单元模型生成门级SAIF。保留A/B/C/scale、原顺序和累加语义；新增片段先走测试侧回归，不把随机数据当真实负载。

## 窗口与活动

- 任务主指标用完整 `task_complete`；计入声明边界内的 fill/drain、stall、配置/切换和转换。短任务完整测量，不 padding 或重复；与 warm-start 成本边界分开。
- K-PE/MN-PE的DP微基准默认使用[dp-fixed-macs-v2](../../hw/power/configs/windows/dp-fixed-macs-v2.json)：**96×1024=98304对有效标量A/B数据=98304 MAC=196608 OP**。H16/Q32/E64每次完整调用处理16/32/64对，需6144/3072/1536次；其他组织用验证后的全DUT满调用容量C_full要求98304%C_full=0。MN-PE并行DP同次调用的有效MAC汇总，不给每路重复分配整个预算后当作等工作量；当前模式所选资源必须完整调用，不允许partial tail、padding或取整。v1仅保留为历史planned配置。
- 初始化/预热后合法排空，正式测完整burst的fill/计算/stall/drain，接受/完成数据对与MAC均精确等于98304。每调用K_call、任务K_job、全DUT的C_full、II、调用数和elapsed cycles分开，stall/重试不重复计数；缺数据不隐式循环。固定工作量时调用数不同；未查稳态则steady_state_status=not_assessed，稳态检查或其他预算另配run，不为凑拍数改变数据量。
- 稳态使用已版本化 [steady-state-v1](../../hw/power/configs/windows/steady-state-v1.json)：合法初始化后，预热至少 max(64, pipeline latency+2, state settle)，同相位 `[start,end)`；1024→2048→4096→8192→16384 拍增长，total 2% / dynamic 5%，增长及两半比较连续两步通过。它是未校准起点，不是行业固定拍数或物理误差保证。
- 目标为三个不同来源片段，各段内判断收敛；跨片段报告差异，不强求相等。不足为 insufficient_trace/coverage_limited，上限未稳定为 not_converged。显式循环只作单列 microbenchmark，重复不增加独立样本。
- RTL/gate 用同源事务及初态，核对独立 golden 关联、数值、周期/计数/last/idle/stall；合法接口初始化非复位状态，不 force 内部零或忽略 X。
- 从 gate 生成准确 scope/窗口 SAIF；直接采集优先，VCD 转换须核验初始值、TC/duty、驻留、边界和 timescale。设计/库/活动变化重新验证，不以 RTL 内部 SAIF 冒充完整门级注释。

## Power Compiler 与正式交付

使用同一 mapped Verilog、DB 和 SDC 只读 link 分析，不在功耗会话 compile/ECO。按安装版本使用 `reset_switching_activity`、`read_saif`、`report_saif`、`report_power` 与 `report_power_calculation`；不能假设存在 `report_switching_activity`。每窗独立清理旧活动，记录精确名称映射和缺项。

验证注释及**实际参与计算的活动**，核对关键 clock/ICG/CP、数据/控制热点和独立 TC/时间。计划总体叶功耗引脚覆盖至少 99%，关键引脚完整覆盖或逐项证明例外；X/Z、未注释和零活动分别判断。无法导出足够有效活动证据时标 unknown，不宣称正式通过。

保留原工况与电气假设；不把全部 CP 强制 100 ps 当作通用修正。功耗原报告可能有不同 dynamic/leakage 单位，逐项转 W。报告 internal/switching/leakage/total，dynamic=前两项；同窗能量、有效 MAC 和 task latency。平均 SAIF 不能提供瞬时 peak，缺项为 null。

关联 DC 面积/setup/hold 和本 power run，保留独立状态/指纹/归档，不回写 DC 摘要。只有功能、活动、电气/时序和相应窗口证据满足，才能交给 characterization；未收敛/诊断/有限片段结果保持其标签。当前 pre-layout、无 CTS/SPEF/可靠物理 glitch，不能称 signoff 或硅片实测。所有产物归本项目 run，清理先查引用，不删除源测试数据、RTL 或源 DC run。
