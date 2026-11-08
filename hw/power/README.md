# 单 DP 真实负载功耗

使用 VCS native gate-level SAIF 和 Synopsys Power Compiler。首批六种架构的 BF16、MXFP8 E4M3、MXFP4 E2M1 共15个兼容点，使用固定 Qwen3-8B MLP 真实负载。方法见 [功耗 skill](../../.skill/power-analysis/SKILL.md)，测量合同见 [实施说明](implementation-plan.md)。

| 位置 | 内容 |
| --- | --- |
| `test/data/power/` | Qwen3-8B 原生K负载、CModel及数学参考 |
| `hw/rtl/<export-id>/` | 与原DC匹配的已验证冻结RTL |
| `hw/dc_syn/runs/<run-id>/` | 原始DDC、网表、SDC及通过的时序证据 |
| `hw/power/plans/` | 显式选择15个架构/格式点及所有输入hash |
| `hw/power/runs/<run-id>/` | 门级结果、原生与补齐SAIF、原始工具报告，本地保留 |
| `hw/power/records/` | 完整测量批次的Markdown、JSON、CSV精简报告 |

## 当前结果

已完成批次 [power_qwen8b_six_1108](records/power_qwen8b_six_1108.md)：六种架构、15个兼容格式点全部通过。静态/动态及内部/开关功耗、总功耗、pJ/MAC和活动审计同时保存在 [JSON](records/power_qwen8b_six_1108.json) 与 [CSV](records/power_qwen8b_six_1108.csv)。原生SAIF、门级输出及原始报告在本地 `runs/power_qwen8b_six_1108/`；该报告引用保护运行及其六份DC输入。

新增 [dp_top 精度寄存器门控比较](records/precision_register_gating_1108.md)：保持共享算术和 L8/II=1，S1–S3 分段使能。在同源负载下 MXFP4 动态功耗降低19.97%，面积增加5.04%；BF16/E4M3 的动态功耗分别降低5.61%/2.33%。新旧网表分别绑定自己的SAIF；原六架构测量仍作为历史比较基线。

新增 [Q32E64 精度寄存器门控比较](records/qe_precision_register_gating_1108.md)：专用 QE lane 保持算术与 L8/II=1，E4M3/MXFP4 动态功耗分别降低1.79%/14.21%，面积增加2.87%，1GHz通过；同源负载的静态、总功耗与时钟活动审计一并保留。

## 执行

先按 [固定依赖](../../dependencies/petile-power.json) 获取MIT解析与审计模块（只提取4个文件，不复制参考工程）：

```bash
python3.11 hw/power/scripts/setup_dependency.py --source-repo /path/to/Quant_LLM_Chip_Codesign
```

本机配置保存到忽略的 `hw/power/configs/machine.local.json`：`setup_script`、`dc_shell`、`iverilog`、`vvp` 和两个匹配N12 base/LVT的 `cell_models` 路径；VCS从setup后的PATH解析。DB直接使用固定DC run的原始resolved配置。禁止提交机器路径、商业库和许可证配置。

```bash
# 输入已选定；需要明确重新选择时才重新生成计划
python3.11 hw/power/scripts/prepare_qwen_plan.py --output hw/power/plans/qwen3_8b_first3.json

# 依次执行：冻结RTL重放 → VCS门级重放/原生SAIF → Power Compiler/活动审计
python3.11 hw/power/scripts/run_power.py --run-id power_<new_name>

# 仅接受15点全部完成且证据hash未变的批次
python3.11 hw/power/scripts/report_power.py --run-id power_<new_name>

python3.11 -m unittest discover -s hw/power/tests -v
```

`--max-points 1` 可用于首点调通，状态为partial，不发布六架构报告。`--resume`只复用已完成且hash一致的点；遇到未完成点保留诊断，使用新run ID重试，不能覆盖失败证据。源码、工具/单元模型或计划变更时也使用新run ID。

使用固定计划中的最终网表，不再按目录时间选择“最新”。E96/E128沿用原快照；`scripts/rtl_gate.verify_power_input`核验原完整回归、冻结源码和本次工作负载重放，不修改旧manifest，也不放宽当前源码综合门禁。该负载下的RTL/网表比对不是全空间形式等价证明。

每点1024笔一次性发射，初始化独立计数；第256笔驱动前开始，第768笔驱动前结束，1GHz下恰好512ns。全部结果、L8/II=1通过后，核验真实功耗引脚无X/Z、Nets/Ports/Pins显式注释100%、所有叶引脚概率/翻转率与SAIF一致。实际关闭的时钟保持实测零翻转。

报告保留Internal、Switching、动态、静态Leakage、Total和pJ/MAC。测量为综合后零延迟、CTS/布线前活动功耗，不包含布线寄生和真实毛刺。TF32/INT8无相应真实负载时不产生实测结论。不支持的架构/格式显示“不支持”，不能填0。

普通运行按 [统一保留入口](../../scripts/README.md#运行产物保留) 保留最近两次已结束且无引用结果；报告引用的功耗运行及其DC输入受到保护，原始SAIF和大型报告只在本机保存。重要节点需要长期pin时先与用户确认具体run。
