# Quant_LLM_Chip_Codesign 功耗方案与 skill 审计

日期：2026-10-24。只读审查本地参考项目 `Quant_LLM_Chip_Codesign`，没有运行其脚本、工具或仿真，也没有修改或迁移其代码、数据和历史结果。以下“已有”指当前参考项目文件所记录/实现的能力，本轮没有重新实验确认历史测量。

参考 checkout HEAD：`0ddc5f7c21082dbce73d992a4d33a5a331f1e0bc`；审查时 `HW/power_analysis/` 无未提交改动。比较目标包括安装的 `petile-power-analysis` skill 与该项目维护源，两者并不完全同步。

## 1. 当前方案实际是什么

```text
冻结并通过数值验证的 RTL
  → DC 网表 + SDC + 工艺库/来源检查
  → 同一 testbench 的 RTL 与门级回放
  → 门级输出逐事务比对 + 周期/协议检查
  → 裁剪到指定窗口的门级 VCD
  → OpenSTA + 匹配 Liberty + 派生 SDC
  → 注释/引脚有效活动审计
  → 原始模型与独立理想时钟 slew 重算
  → 平均功耗分量、能效和 PPA 报告
```

关键证据位于参考根目录下：

| 文件 | 核查结论 |
| --- | --- |
| `HW/power_analysis/README.md` | 明确零延迟门级、输入循环、窗口、覆盖和当前时钟修正；含历史批次及限制 |
| `HW/power_analysis/run_power.py` | 同负载 RTL/gate 仿真、结果比对、窗口裁剪、hash、SDC 适配；单点原模型估计 |
| `HW/power_analysis/power.tcl` | 读 Liberty、网表、SDC 和 VCD，检查覆盖后调用 OpenSTA `report_power`；未读取 SPEF/SDF |
| `HW/power_analysis/clock_slew.tcl` | 独立设置完整时钟路径的理想 slew，检查不误选 D/Q/使能；不直接改活动率 |
| `HW/power_analysis/analyze_internal_power.py`、`detail_power.tcl` | 逐单元/引脚活动与功耗审计，用于发现仅靠覆盖率无法发现的限幅 |
| `HW/power_analysis/run_ratio_power.py`、`report_ratio_power.py` | 批量流程、时钟模型选择、时序/活动审计及报告；不能把单点原模型 PASS 当作完整 PPA PASS |
| `HW/power_analysis/build_opensta.sh` | 固定 OpenSTA 与 CUDD commit，构建位置在参考项目本地工具目录 |

这是**真实数值驱动、综合后、零延迟门级活动的平均功耗估计**，比默认活动或只按面积/位宽推功耗充分得多。它不是 post-layout 或硅片功耗测量。

## 2. 值得继承和需要加强的部分

| 维度 | 参考方案已有能力 | DP-Puzzel 建议 |
| --- | --- | --- |
| 输入来源 | 固定向量、模型版本/来源、输入 hash；不同格式同源 | 保留，并增加真实 forward trace、不同层与任务阶段 |
| 功能一致性 | 同负载 RTL/gate bit-exact，协议/计数；历史独立 golden | 保留；按本项目 export ID 和统一验证门禁接入 |
| 窗口 | 初始化、64 拍 warmup、1024 拍 steady-state，精确裁剪 | 不照抄周期数；按流水与采样收敛确定，另加任务完成窗口 |
| 活动完整性 | VCD identifier 大小写、叶功耗引脚、X/Z、至少 99% 注释 | 保留；明确统计分母、关键引脚与传播/默认活动占比 |
| 有效活动 | 后续增加逐 CP/D/Q 与时钟网络审计 | 作为正式结果的必需门禁；不要仅在出现异常后手动调查 |
| 时钟 | 原模型与独立 100 ps 理想网络重算，不改旧报告 | 有依据的理想假设 + 敏感性；有 CTS 后替换，不固定抄 100 ps |
| 工艺 | N22/N12、Base/LVT 对应库，单元和端口核查 | 不照抄 PVT/路径/频率；优先配套 release 并核查电气数据 |
| 物理模型 | 明确 ZeroWireload、无 CTS/SPEF/SDF | 用证据阶段标记；具备环境后加入物理数据和延迟活动 |
| 工具 | 固定版本 OpenSTA/Liberty，记录输入与脚本指纹 | 先查 DC/Power Compiler 功能，条件允许做同输入交叉核对 |
| 报告 | Internal/Switching/Leakage、W→mW、pJ/MAC、2 OP/MAC | 保留平均功耗；另交付 stall/idle、任务能量、采样与模型误差 |
| 可比性 | 已披露历史重综合、不同网表与输入限制 | 精度对比尽量使用同一物理网表；严格区分跨工艺、映射和格式效应 |
| 归档 | 保存摘要、hash、审计；部分历史网表/VCD按用户要求清理 | 论文关键输入提供可恢复归档；hash 不能替代原文件 |

本项目建议见[完整方案](no-primetime-methodology.md)，不能从上述参考能力推断 DP-Puzzel 已有相同 runner。

## 3. 时钟活动与 100 ps 处理

参考报告 `HW/power_analysis/reports/PETileBF16_Internal_0921192706/SUMMARY.md` 记录：历史 BF16 测点的活动注释为 100%，但 5681 个寄存器 CP 的有效活动率相对直接 VCD 计数低超过 1%。报告将该分析标为 `ATTRIBUTION_ONLY_ACTIVITY_CLIPPED`。

本轮也只读检查了参考本地 OpenSTA 源码。固定 commit 为 `efe207d0c7070c983cdc3af5b6437e3765639ddf`；`power/Power.cc` 的 `PropActivityVisitor::setActivityCheck` 在正 slew 下将活动密度限制到 `1 / getMinRfSlew(pin)`。**来源标签仍为 VCD，不保证最终参与计算的密度没有变化。**这解释了为何仅有 annotation PASS 不够。

当前维护流程通过 `clock_slew.tcl` 对识别出的时钟源、门控路径和 CP 统一施加 0.10 ns min/max rise/fall slew，并在独立 OpenSTA 会话重新计算；数据 D/Q 和使能不使用该覆盖。随后逐引脚核对活动，门控关闭支路仍须为零翻转。旧报告不被覆盖。

应这样评价这一处理：

- **合理之处：**明确承认 pre-CTS 模型问题，保存前后证据，重新查库计算，并补上有效活动审计；没有把所有门控时钟直接设成满频。
- **剩余假设：**所有这些引脚统一 100 ps 并非布局后的物理结果；该设置同时影响活动限幅与内部功耗查表，不能称为仅“纠正计数”。
- **标准化方向：**CTS 前声明并验证时钟模型、展示敏感性；CTS 后使用实际时钟网络、传播 slew 和寄生。不能把全网 `set_assigned_transition` 当作签核规范或无条件套用到其他工艺。

当前 README 还披露了 N12 某例重算相对原模型显著变化。那是模型假设变化的参考案例，不是本项目数据，也不能当作通用修正比例。

## 4. 真实输入的代表性

主要证据：`HW/power_analysis/reports/PETile4_AllFormats_1023095508/ANALYSIS.md`、该目录的来源回执，以及 README 的“显式选择格式与真实模型负载”说明。

| 项目 | 参考文件所记录的事实 | 对结论的影响 |
| --- | --- | --- |
| Qwen 输入 | Qwen3-0.6B 的 embedding、第一层 RMSNorm 和 q_proj 权重，512 个局部样本 | 使用真实模型参数构造局部算子输入；没有捕获整网多层 forward |
| Qwen tokenizer | 历史采用 Qwen2.5 tokenizer 与 Qwen3 参数的组合 | 不能称为官方 Qwen3 tokenizer 下完整推理 trace |
| A/B 配对 | 匹配通道切片；固定 seed 选择输出行与起始列 | 有数值对应关系，但事务顺序不等价于完整 GEMM 的复用/调度 |
| Qwen C | 由激活元素乘系数派生 | 不是该 q_proj 的真实 bias，也不代表 K 分块的真实累加状态 |
| DeepSeek 输入 | DeepSeek-R1-Distill-Qwen-1.5B 的 256 个局部样本，C 为匹配通道真实 bias | 增加一个分布对照，仍是局部样本边界 |
| 测量时间 | II=1、预热后循环到 1024 拍 | 满流水持续计算；不含真实存储停顿及完整任务完成时间 |
| 格式 | 当前报告已扩展 E5M2、NVFP4、HiF4 等 | 不能只根据旧 skill 的三格式默认推断当前实验范围；也不能据同名格式采纳未经确认的数值规范 |

这些限制是参考项目自己披露的事实，不意味着其局部硬件比较没有价值。适当表述是“真实模型派生局部输入下的稳定窗口估计”；若用于完整模型平均功耗，缺少多层采样、实际运行轨迹和调度占用依据。

参考报告还明确：部分旧网表清理后重新综合，新旧功耗在同一 RTL 下来自不同网表 hash。即使面积一致，也不能断言映射完全相同；要严格隔离格式效应，应在保留的新网表上重测全部对照格式，并另存结果。本轮未执行这种重测。

## 5. skill 与维护实现存在同步差异

本轮实际读取了安装 skill 和参考项目维护 skill：

- 安装版记载历史 N22 TT 0.9 V / 25°C、三格式和旧 canonical 配置等默认内容。
- 维护源补充了 85°C、N12 Base/LVT、库/模型 release 与备份映射等信息，但主要操作说明仍偏早期流程，尚未完整表达当前 README 的全时钟网络 slew 重算与逐引脚有效活动验收。
- 当前 `CURRENT_CONFIG.md` 与 README 包含 100 ps 模型和活动限幅背景；`CURRENT_CONFIG.md` 中还有针对特定历史批次的 hold/范围说明，不能无条件解读为所有新批次的状态。

因此，应按**明确 run 的 manifest、脚本版本和逐点验收回执**判断结果，README 用作导航，skill 用作操作指引；发生冲突时查原始证据，不根据“当前”标题猜测。后续若为 DP-Puzzel 编写 skill，应把有效活动、时钟模型与状态判据纳入正文，指向本项目公共入口；只放 `.skill/<name>/SKILL.md`，不复制参考项目的技能目录布局、私有路径或全部源码。

本轮用户要求的是调研与方案，未创建新功耗 skill，也未修改外部已安装 skill。

## 6. 什么算“更标准”

1. **工具链衔接：**有相应功能/授权时，DC/Power Compiler + 代表性 SAIF 是更直接的 Synopsys 综合阶段路线。只有 DC 综合能力时，OpenSTA + Liberty + 门级活动仍是可审计的平均功耗路线。官方方法依据见[方案第 5、6 节](no-primetime-methodology.md#5-路线-a门级活动--saif--dc--power-compiler)。
2. **数据交换：**采用 VCD/SAIF、Liberty、SDF/SPEF 等通用输入并保存来源，不把后缀或工具名当作准确度证明。SAIF 不是把零延迟 VCD 变成真实毛刺的手段。
3. **物理证据：**提高绝对准确度的主要增量是同源 CTS/寄生/延迟活动及合适的功耗模型；标准不是从 OpenSTA 换成另一个 `report_power` 命令。
4. **研究证据：**真实采样、时间顺序与调度、有效活动审计、可比条件、独立验证误差和可恢复归档，应比单个“功耗 PASS”更优先。

## 7. 本轮参考指纹

以下路径均相对参考项目根目录，避免提交机器私有路径；本项目不跟踪该参考源码。SHA-256 对应本次实际读取内容，后续内容改变应重新审查。

| 路径 | SHA-256 |
| --- | --- |
| `HW/power_analysis/README.md` | `f916e117420f1b3cc16fd62023df6cffa5412345543647dd0b2fddf225d5fc91` |
| `HW/power_analysis/CURRENT_CONFIG.md` | `c29f834007d9f53d972c27c469f95a6e62caee80eda207a2879fc37de2d2c143` |
| `HW/power_analysis/skills/petile-power-analysis/SKILL.md` | `e578dff6ba3390ef394e09b70e4e975b07b6811d617818b19dd00575c0212792` |
| `HW/power_analysis/run_power.py` | `ecb78d0c62c08967cc29b4f6bdcdaee76eaa74ef7cb5236312ad751223a3cb20` |
| `HW/power_analysis/power.tcl` | `b6077018cef5a2523fac4e4bcc85070e6b68519e11f401fce5ee0d7a9076a21f` |
| `HW/power_analysis/clock_slew.tcl` | `5e795b8054920359544c0a112bd33ede558446bb4775f9b4b8388bd3cf3b8564` |
| `HW/power_analysis/build_opensta.sh` | `92dd95885b95b58df9d38f06b527ca5ff0af3ad989f6ec8bf1e919e0f2bdd299` |
| `HW/power_analysis/reports/PETile4_AllFormats_1023095508/ANALYSIS.md` | `9ef86e7bfe8d8b76062f209559d6e25fdabde3da4d735d7676a83c1ddb7181f3` |
| `HW/power_analysis/reports/PETileBF16_Internal_0921192706/SUMMARY.md` | `41a0ea07fe34ba7f2c3e7efb0506f4fdf6affc8d25de72ab8f7adeefce50993e` |
| `HW/power_analysis/run_ratio_power.py` | `885ce53c4c98c6173ca32bb2c8d0459e500d5ecf08656983b69c5a16d779c16b` |
| `HW/power_analysis/report_ratio_power.py` | `9becb1c4585267d496d3c7cc429cced55dbc33b678230dcc33a39e71cafe00b2` |

另外两个读取对象的逻辑位置与 SHA-256：安装的 `petile-power-analysis/SKILL.md` 为 `be27d6e4d88d03a457438887ff4e5bdaff606dfee281e6150ae8842094a5d81a`；参考本地 OpenSTA 源码 `power/Power.cc` 为 `69ea8c88144f1a6a9fd08b992f798ddafa9bf916d9433638ccf882f279c1bcd7`。

`build_opensta.sh` 同时固定 CUDD 为 `f54f533303640afd5dbe47a05ebeabb3066f2a25`。固定 OpenSTA 的 GitHub 页面本轮未能由浏览工具取得，活动限幅结论来自参考项目本地对应 commit 的源码及审计报告；不把远程访问失败写成外部验证成功。上游实时文档仅用于核查通用能力，不能替代该固定版本的行为。
