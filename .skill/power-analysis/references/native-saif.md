# 单 DP 原生 SAIF 测量协议

## 输入与预检

- 记录 Git 提交、明确的 export ID、DC run ID、目标格式、数据集和窗口。用 `python3 scripts/rtl_gate.py EXPORT_ID` 核对当前 RTL 证据。核对 `inputs/resolved.json`、`DC_COMPLETE`、`summary.json` 和原始报告。当前单 DP 为 `dp_top`、`clock`、同步高有效 `reset`，已综合参数为 `K_FP16=16, LOCAL_W=27, GLOBAL_W=40`，L8、II=1。
- 确认原始 `netlist/dp_top.ddc`、`dp_top.sdc`、`dp_top_mapped.v` 齐全，网表和映射数据库来自同一 run。核验实际链接库和 VCS 单元模型的工艺、发行版、base/LVT 和引脚。VCS、DC/Power Compiler 版本和许可证以本机实际运行验证。`power_ready` 保持原记录值，功耗流程另存自己的匹配、活动和注释证据。
- 首个候选是已通过时序的 `dc_dp_top_11050215`，TSMC CLN12FFCLL TT 0.7 V / 85 °C、1 GHz、ZeroWireload、base/LVT。后续改动以新通过的 RTL、网表和回执为准。该历史 hold 修复 run 的首轮证据在本机归档，按 [DC 记录说明](../../../hw/dc_syn/records/README.md) 取用。

## 同源真实负载

在 `test/data/dp/<format>/K<logical_k>/correct_961/manifest.json` 中按 `dataset` 精确选段。核对 `input_sha256`、`golden.expected_sha256`、段起止、事务数、`raw_sample_sha256`、模型 revision 和 C 策略。读取对应的 `inputs.txt` 与 `expected.jsonl` 行，不改变 A/B/C/scale 和 HiF4 metadata 的端口布局。跨格式比较要求同一底层样本集和同一窗口策略。

`batch512_ai_load` 来自 Qwen3-0.6B 第 0 层 q_proj 权重及 embedding/RMSNorm 局部激活，C 是激活派生的 FP32 加数。它代表模型算子切片。选中 512 个源事务后，按原顺序各发射一次。可使用 `dp-ai512-middle256-v1`，发射拍 `[0,128)` 预热、`[128,384)` 测量、`[384,512)` 继续发射并排空。1 GHz 的测量窗口为 256 ns。若获得同源的 1024 笔数据，可单独命名采用 `[256,768)` 的 512 拍窗口。记录实际的源样本数、发射数和窗口，不将循环回放计为新增样本。

| 格式 | 满载 MAC/周期，K_FP16=16、II=1 |
| --- | ---: |
| FP16、BF16 | 16 |
| MXFP8 E4M3/E5M2、MXFP6 E2M3/E3M2 | 32 |
| MXFP4 E2M1、NVFP4、HiF4 | 64 |
| TF32、INT8 | 8、32，当前无同源模型数据 |

## 仿真与活动审计

1. 使用同一份 packed 端口激励和独立期望。复用 `test/rtl_tb/dp_tb.v` 的握手、L8、结果、类型和 `last` 检查。实现门级入口时实例化固定参数的映射顶层，禁用仅针对 RTL 层级的断点。所有精度通路通过合法初始化输入进入已知状态，验证初始化结果。保持测量窗内 II=1、精度固定且无复位。每个格式重跑门级仿真并保存完整输出匹配证据。
2. 对 VCS 使用与库模型相配的零延迟门级配置。参考选项为 `-full64 -sverilog -debug_access+all +vcs+saif_libcell +notimingcheck +delay_mode_zero`。核对实际仿真时间单位和时钟周期。以 DUT 层级为 scope，在发射边界调用 `$set_gate_level_monitoring`、`$set_toggle_region`、`$toggle_start`、`$toggle_stop` 和 `$toggle_report`。记录开始、结束时间与 SAIF timescale。标准流程直接使用原生门级 SAIF。
3. 枚举映射网表顶层端口的全部位、真实叶单元引脚和时钟对象。检查窗口时长与 `DURATION × TIMESCALE` 一致，状态时间完整且真实引脚 `TX=TZ=0`。VCS 若省略 `celldefine` 内叶引脚，只能从网表证明相同电气网络的 `T0/T1/TC` 或真实连接常量，保留逐引脚 alias 证据。缺失、多义或不支持的表达式使审计失败。
4. 在 Power Compiler 链接原 DDC 与匹配 DB，保留原时钟及 IO 约束。清除既有活动后用 `read_saif` 注释，核对实例名和实际时间单位。检查 `report_saif` 的 Nets、Ports、Pins 显式注释均为 100%，传播和默认补齐均为零。把实际叶引脚与时钟引脚的概率和翻转密度同 SAIF 的 `T1 / DURATION`、`TC / duration_seconds` 对照。保留关断时钟的零翻转统计。
5. 以原 DC 时钟转换时间为基线，核查时钟端口、门控时钟输入/输出和触发器 CP 的 rise/fall、min/max。当前 N12 DP 为 0.10 ns。数据端和门控使能端按原约束处理。保存 `report_annotated_transition`、原始功耗、活动覆盖、逐引脚审计、时序与工具日志。

## 结果口径与产物

- 保留各列原始单位并统一转为 W 或 mW，再检查 Internal + Switching + Leakage 与 Total 的工具舍入残差。`Dynamic = Internal + Switching`。Power Compiler 的 clock network 分组可能含触发器时钟脚内部能量，比较时使用同一工具口径。
- `MAC/s = active_MAC_per_cycle × frequency_Hz`。`pJ/MAC = Total_W / (MAC/s) × 10^12`。若报告 TOPS/W，按 `2 OP/MAC` 换算。按格式同时报告整 DP 的 mW 和 pJ/MAC，C 加数不额外计 MAC。
- 记录 `window_energy_J = Total_W × duration_seconds`，附数据集、PVT、频率、工作窗口、工具版本、RTL 指纹和 DC run。结果是综合后零延迟活动驱动的窗口平均功耗，适用边界为原库和负载、CTS 与布线前。
- `hw/power/runs/<run-id>/` 保存计划、激励与匹配、原生 SAIF、别名展开 SAIF、时钟/活动审计和原始报告。可压缩 SAIF 归档。`hw/power/records/` 仅发布通过证据核验的核心结果和适用范围。网表、PDK、本机配置和大量活动文件留在本地。
