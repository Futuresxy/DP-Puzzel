# 单 DP 真实负载功耗

六架构的设计验证、时序和优化分析见 [v1.9 设计交付](records/v19_design_report_20261110.md)。功能分布见 [七类面积](../../paper/data/H16Q32E64_area/README.md) 和 [三种精度的总功耗](../../paper/data/H16Q32E64_power/README.md)。

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

先看 [实验记录与当前结果索引](records/README.md)。[当前完整报告](records/latest_six_retained.md)、[CSV](records/latest_six_retained.csv)、[JSON](records/latest_six_retained.json) 汇总六种 DP 的15个兼容点，包含动态、静态和总功耗。

2026-11-10 用户授权清理被替代的历史运行大产物，保留当前六架构及必要依赖。历史报告和对比数值仍保存在 `records/`，但其中旧 run 链接可能已退役。[原 v1.9 对照报告](records/v19_six_architectures_20261110.md)不改写历史数值。当前复核使用 [保留批次选择文件](plans/latest_six_retained.json)，使用[退役回执](../dc_syn/maintenance/final_six_dependency_retirement.json)及最终功耗批次保存的负载证据；它用于报告审计，不是 `run_power.py` 的仿真输入计划。删除明细见 [维护回执](../dc_syn/maintenance/latest_six_artifacts_cleanup_20261110.json)。

## 执行

先按 [固定依赖](../../dependencies/petile-power.json) 获取MIT解析与审计模块（只提取4个文件，不复制参考工程）：

```bash
python3.11 hw/power/scripts/setup_dependency.py --source-repo /path/to/Quant_LLM_Chip_Codesign
```

本机配置保存到忽略的 `hw/power/configs/machine.local.json`：`setup_script`、`dc_shell`、`iverilog`、`vvp` 和两个匹配N12 base/LVT的 `cell_models` 路径；VCS从setup后的PATH解析。DB直接使用固定DC run的原始resolved配置。禁止提交机器路径、商业库和许可证配置。

```bash
# 例：使用本轮E96的固定输入计划重新测量；使用新的run ID
# 依次执行：冻结RTL重放 → VCS门级重放/原生SAIF → Power Compiler/活动审计
python3.11 hw/power/scripts/run_power.py \
  --plan hw/power/plans/v19_t8h16q32e96_1110.json \
  --run-id power_<new_name>

# 核验当前选定的六架构15点；新增测量经审查后显式更新选择文件
python3.11 hw/power/scripts/report_current_six.py \
  --selection hw/power/plans/v19_six_architectures_20261110.json \
  --output hw/power/records/v19_six_architectures_20261110

python3.11 -m unittest discover -s hw/power/tests -v
```

`--max-points 1` 可用于首点调通，状态为partial，不发布六架构报告。`--resume`只复用已完成且hash一致的点；遇到未完成点保留诊断，使用新run ID重试，不能覆盖失败证据。源码、工具/单元模型或计划变更时也使用新run ID。

使用固定计划中的最终网表，不再按目录时间选择“最新”。各点使用计划中明确指定的已验证快照；`scripts/rtl_gate.verify_power_input`核验原完整回归、冻结源码和本次工作负载重放，不修改旧manifest，也不放宽当前源码综合门禁。该负载下的RTL/网表比对不是全空间形式等价证明。

并行修改 CModel 时，可在运行计划的每个点显式指定 `reference_model: {"directory": "hw/power/runs/<reference-snapshot>", "manifest_sha256": "<sha256>"}`。快照包含 `dp_cmodel_cli`、`sources/` 下按仓库相对路径保存的完整模型源码，以及记录 `sources` 和 `binary_sha256` 的 `reference.json`。运行器校验快照 manifest、实际源码和实际可执行文件的 SHA-256，同时要求身份与数据集 manifest 一致；路径不能越出项目。未指定时仍检查当前 CModel 源码与构建。源码/构建冻结应在生成对应 expected 之前完成，不能给未知可执行文件补写一个 hash 便宣称已经验证。

固定 reference 只决定初始化和 expected 的模型来源，不改变冻结 RTL、完整回归及本次 RTL/门级负载比对门禁。若架构语义发生变化，应在独立派生数据集中重算 CModel expected 并保留数学参考和原始负载身份；不要覆盖旧数据集。运行计划引用的模型快照与派生数据同样是受保护的分析依赖。

新架构点通过 `cmodel_config` 显式绑定数值配置（例如 `architecture_v19: true`）；该对象必须与派生数据集 manifest 一致，并完整传给初始化参考计算。`frontend` 默认取点的 `cmodel_frontend`，重复声明时必须一致。v1.9混合/QE点使用 true，保留原E64合同的点使用 false；不能因二进制支持新版便自动迁移旧架构。

每点1024笔一次性发射，初始化独立计数；第256笔驱动前开始，第768笔驱动前结束，1GHz下恰好512ns。全部结果、L8/II=1通过后，核验真实功耗引脚无X/Z、Nets/Ports/Pins显式注释100%、所有叶引脚概率/翻转率与SAIF一致。实际关闭的时钟保持实测零翻转。

报告保留Internal、Switching、动态、静态Leakage、Total和pJ/MAC。测量为综合后零延迟、CTS/布线前活动功耗，不包含布线寄生和真实毛刺。TF32/INT8无相应真实负载时不产生实测结论。不支持的架构/格式显示“不支持”，不能填0。

普通运行按 [统一保留入口](../../scripts/README.md#运行产物保留) 保留最近两次已结束且无引用结果；报告引用的功耗运行及其DC输入受到保护，原始SAIF和大型报告只在本机保存。重要节点需要长期pin时先与用户确认具体run。
