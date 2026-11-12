# 功耗实验记录与最新结果

**日常查功耗先看本页。** 2026-11-12 扩展批次独立记录，原 2026-11-10 六种 DP、15 个兼容精度点继续保留。

## 2026-11-12 扩展批次

[前三种九点完整汇总](first_three_expansions_20261112.md) · [相对 v1.9 基线](first_three_vs_v19_baseline_20261112.md)。两者均保留 JSON/CSV，基线引用原测量而未重测。

Q64E64 三点已全部通过：[动态/静态/总功耗](q64e64_20261112.md) · [CSV](q64e64_20261112.csv) · [JSON与来源](q64e64_20261112.json)。BF16 K16、MXFP8 E4M3 K64、MXFP4 K64 总功耗分别为 **15.943218 / 26.908993 / 11.682611 mW**。

E192 三点已全部通过：[动态/静态/总功耗](e192_qwen8b_20261112.md) · [CSV](e192_qwen8b_20261112.csv) · [JSON与来源](e192_qwen8b_20261112.json)。BF16 K16、MXFP8 E4M3 K32、MXFP4 K192 总功耗分别为 **15.821221 / 16.549736 / 23.463076 mW**。

E256 三点已全部通过：[动态/静态/总功耗](e256_power_20261112.md) · [CSV](e256_power_20261112.csv) · [JSON与来源](e256_power_20261112.json)。BF16 K16、MXFP8 E4M3 K32、MXFP4 K256 总功耗分别为 **16.063122 / 16.635698 / 29.381828 mW**。

T8H16Q96E192/T8H16Q128E256 在基础四组上增加 8/12 个 QE 组，功能已验证，独立 DC 正在执行；时序通过后再测真实负载功耗。更大 K 的输入已[导入本项目](../workloads/petile_extended/README.md)，不能把导入数据当作已测功耗。

## 原六架构保留结果

[当前完整报告：动态/静态/总功耗](latest_six_retained.md) · [CSV](latest_six_retained.csv) · [JSON与来源](latest_six_retained.json) · [DC记录入口](../../dc_syn/records/README.md) · [七类总功耗图](../../../paper/data/H16Q32E64_power/README.md)

工况：N12 TT / 0.7 V / 85°C，1 GHz，ICG 开启。Qwen3-8B MLP down_proj，1024 笔独立请求，512 ns 稳态活动窗口；VCS native gate-level SAIF + Power Compiler。以下为总功耗 mW；不支持的精度用 —，不是零功耗。

| 架构 | BF16 mW | MXFP8 E4M3 mW | MXFP4 E2M1 mW | 工作目录 |
|---|---:|---:|---:|---|
| T8H16Q32E64 | 15.328264 | 16.001999 | 11.196534 | [power_baseline_v18_repaired_1109](../runs/power_baseline_v18_repaired_1109/) |
| T8H16Q32E96 | 15.637100 | 16.354448 | 14.417467 | [power_v19_t8h16q32e96_1110](../runs/power_v19_t8h16q32e96_1110/) |
| T8H16Q32E128 | 15.893229 | 16.619942 | 17.594673 | [power_v19_t8h16q32e128_1110](../runs/power_v19_t8h16q32e128_1110/) |
| T8H16Q64E128 opt | 15.744144 | 28.788990 | 20.563437 | [power_v19_t8h16q64e128_opt_1110](../runs/power_v19_t8h16q64e128_opt_1110/) |
| E64 | — | — | 7.036236 | [power_e64_fresh_saif_1109](../runs/power_e64_fresh_saif_1109/) |
| Q32E64 | — | 13.580442 | 10.217557 | [power_v19_q32e64_1110](../runs/power_v19_q32e64_1110/) |

每个工作目录下 `<top>__<format>/` 包含 `power.rpt`、`hierarchy_power.rpt`、`power_audit.json`、原生/注释 SAIF、RTL/门级比对结果。`point.json` 固定该点的网表、RTL、数据和哈希。当前 CModel 参考为 `v19_reference_1109`。旧 `baseline_v18_reference_1109` 已删除。基线三个已测点的原输入与 golden 随各点存入 `workload_evidence/`，供报告复核使用。`functions_v19_1109` 保存当前七类功能统计。

## 历史数值与对比

2026-11-10 按用户要求删除旧实验大产物，保留本目录历史 MD/JSON/CSV。旧报告中的运行目录可能已不存在；其数值作为历史记录，不能当作仍有完整本地证据的现用输入。

| 实验 | 记录 | 原始产物状态 |
|---|---|---|
| 当前六架构 | [当前完整报告](latest_six_retained.md) | 15 点全部保留并可重新审计 |
| v1.9 与旧门控批次比较 | [原对照报告](v19_six_architectures_20261110.md) | 新批次完整；旧批次仅保留数值摘要 |
| baseline v1.8 电气修复后功耗 | [记录](baseline_v18_repaired_1109.md) | 保留，为现用 baseline |
| E64 新 SAIF | [记录](e64_fresh_saif_1109.md) | 保留，为现用 E64 |
| 旧门控六架构 | [记录](current_six_precision_gated.md) | 旧运行大产物已清理 |
| 原六架构基线 | [记录](power_qwen8b_six_1108.md) | 旧运行大产物已清理 |
| baseline / QE 门控实验 | [baseline](precision_register_gating_1108.md)、[QE](qe_precision_register_gating_1108.md) | 旧运行大产物已清理 |
| baseline 与 E64 lane 诊断 | [记录](gated_vs_e64_lane_1108.md) | 旧运行大产物已清理 |

总设计分析：[v1.9 交付报告](v19_design_report_20261110.md)。清理明细：[维护回执](../../dc_syn/maintenance/latest_six_artifacts_cleanup_20261110.json)。

## 复核与后续记录

当前选择文件使用[退役回执](../../dc_syn/maintenance/final_six_dependency_retirement.json)复核现有测量。重跑原基线功耗需准备匹配的参考模型和负载计划。报告复核命令如下。

```bash
python3.11 hw/power/scripts/report_current_six.py \
  --selection hw/power/plans/latest_six_retained.json \
  --output hw/power/records/latest_six_retained
```

每次新实验增加带日期/版本的 MD、JSON、CSV，记录目的、绑定 DC/export ID、负载/窗口/频率/PVT、SAIF 审计、动态/静态/总功耗和与上一版对比；更新本页当前链接。保持旧数值不变，清理原始产物时记录状态。功耗是综合后、CTS/布线前测量，不包含阵列互连/SRAM和真实布线毛刺。
