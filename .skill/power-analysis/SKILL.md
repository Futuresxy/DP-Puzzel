---
name: power-analysis
description: Plan or run single-DP workload power comparisons in DP-Puzzel using VCS native gate-level SAIF and Synopsys Power Compiler. Use for precision-specific activity, annotation audits, and power per MAC.
---

# 单 DP 真实负载功耗

读取根 [AGENTS.md](../../AGENTS.md)、[功耗目录](../../hw/power/README.md) 和 [DC 输入契约](../../hw/dc_syn/input-contract.md)。任务要求搭建 skill 或讨论架构时，只整理方法和所需证据。任务授权实际测量时，先做输入预检，再按 [原生 SAIF 测量协议](references/native-saif.md) 执行。当前仓库尚无单 DP 的自动化功耗入口或实测结果。

1. 显式选择 `hw/rtl/<export-id>/` 的已验证快照和 `hw/dc_syn/runs/<run-id>/` 的完整映射结果。核对 RTL 门禁、输入指纹、参数、顶层、DC 结果、DDC/SDC/网表和实际库/模型。默认比较同一份已通过 setup/hold 的网表。时序违例的诊断实验单独标注，不能作为达标频率的功耗点。
2. 固定工艺、PVT、时钟、约束和活动窗口。不同格式使用同源激活与权重，按各自格式编码及缩放。当前可从已提交数据中选择 Qwen3 `batch512_ai_load` 的九种浮点编码。先读 manifest 核对来源与实际行段。TF32 和 INT8 等有匹配的真实负载再加入。
3. 先在已验证 RTL 上重放整个事务流，再用匹配的单元模型在 VCS 中运行映射网表。对照独立期望逐笔核对输出、类型、`last`、L8 和事务计数。复位、合法初始化、填充与排空均在测量窗之外。以 VCS 原生门级 SAIF 记录被测窗口。
4. Power Compiler 读取原 DDC、对应 DB 和 SAIF。核查时钟网络转换时间、SAIF 时长、真实功耗引脚无 X/Z、Nets/Ports/Pins 全部显式注释，以及每个叶引脚和时钟引脚的实测概率与翻转率。仅允许从已证明电气等价的标量连线或常量补全被省略的引脚记录。
5. 每个格式记录 Internal、Switching、Leakage、Total、mW、有效 MAC/周期与 pJ/MAC，关联同一网表和同源负载。保存原始 SAIF、窗口、匹配结果和工具报告。精简结果和适用范围放入 `hw/power/records/`，原始工具产物保存在忽略的 `hw/power/runs/`。

输入不完整、重放不一致或注释审计失败时保留诊断结果，并指出具体缺项。工具、许可证、PDK 和库路径只在本机解析。流程借鉴 [PETile 功耗 skill](https://github.com/Futuresxy/Quant_LLM_Chip_Codesign/blob/5a5037ad03b656ea975ef594d0aca4dc5ef96a39/HW/power_analysis/skills/petile-power-analysis/SKILL.md)，DP 的接口、负载和结果均取自本项目。

记录功耗 run 的完成状态及所用 DC run，结果确认后按 [运行产物保留](../../scripts/README.md#运行产物保留) 清理。长期保留须与用户确认具体 run。
