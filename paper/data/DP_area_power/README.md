# DP 面积与功耗数据及绘图

## 最新六种 DP：N12 / 1GHz

`latest6_area.csv` 保存六种架构的综合面积、组合/时序面积、工况、DC run 和冻结 RTL export ID。
`latest6_power.csv` 保存 15 个实测格式点的 Internal、Switching、动态、静态、总功耗、K、pJ/MAC，以及功耗审计和负载验证回执路径/hash。
来源为 [`latest_six_dp.json`](../../../hw/dc_syn/records/latest_six_dp.json) 和
[`current_six_precision_gated.json`](../../../hw/power/records/current_six_precision_gated.json)；
`latest6_sources.json` 固定来源文件 SHA-256、负载窗口和工况。

| 图中 H:Q:E 配比 | 架构 | 顶层 |
| --- | --- | --- |
| 0:0:4 | E64 | dp_top_e64 |
| 0:2:4 | Q32E64 | dp_top_q32e64 |
| 1:2:4 | T8H16Q32E64 | dp_top |
| 1:2:6 | T8H16Q32E96 | dp_top_t8h16q32e96 |
| 1:2:8 | T8H16Q32E128 | dp_top_t8h16q32e128 |
| 1:4:8 | T8H16Q64E128 opt | dp_top_t8h16q64e128_opt |

配比为 H/Q/E 原生 MAC/cycle 除以 16；共享单元的不同模式不能同时相加。
功耗图横向排列三个子图：**(a) BF16、(b) MXFP8 E4M3、(c) MXFP4 E2M1**，分别为 4、5、6 根柱。
每根柱只展示工具报告的 **total power**，三个子图共用纵轴范围；未测或不支持的组合不填零。
面积倍率以 `dp_top` 为基准；所有功耗倍率统一以 `dp_top / BF16` 为基准。
总功耗保留工具原值，动态=Internal+Switching，静态=Leakage；当前分项和与总值最大差约 0.00030 mW，校验容差为 0.0005 mW，绘图不改写测量值。

在仓库根目录运行（Python 环境需安装 `paper/requirements.txt`）：

```bash
# 从当前 HW 索引重新导出数据，并生成两张 PNG。
python3.11 paper/data/DP_area_power/plot_latest6_area_power.py --refresh-data
# 仅从本目录已保存的 CSV 重绘。
python3.11 paper/data/DP_area_power/plot_latest6_area_power.py
```

输出为 `paper/figures/latest6_area.png`、`latest6_power.png`（400 dpi），
同目录 `latest6_plot_manifest.json` 记录数据/脚本/图片 hash、基准和柱数。
支持 `--output-dir` 与 `--dpi`；脚本沿用 `plot_area_power.py` 的浅色柱、橙色基准框、数值标签及竖直倍率括号，功耗使用总值单柱。

测量条件：N12 TT / 0.7V / 85°C、1GHz、L8/II=1、ICG 开启；五种共享架构采用精度寄存器门控，E64 保持原设计。
Qwen3-8B 第 0 层 MLP down_proj 同源 1024 笔输入，发射索引 256..767 的 512ns 窗口；VCS 原生门级 SAIF + Power Compiler。
三个混合架构使用本轮测量，dp_top/Q32E64/E64 复用索引中已验证的对应测量。
这是已有测量的汇总，范围为综合后零延迟、CTS/布线前，无 SDF/SPEF；不同 K 的整 DP 功耗比较需结合容量与 pJ/MAC。

## 原 Select8 数据与图片

仅包含八种配置：`1:0:0`、`0:0:4`、`0:2:0`、`0:2:4`、`1:2:4`、`1:2:6`、`1:2:8`、`1:4:8`。不包含 selected14 或 21 配置合并流程。

修改以下 CSV 后运行 `python3 plot_area_power.py`，或在 `paper/` 下执行 `make cost-figures`：

- `selected8_area.csv`：每种配置一行，只修改 `area_um2` 即可更新面积。`H/Q/E` 为 MAC/cycle，等于配比数字乘 16；`process` 与 `frequency_mhz` 记录共同测试条件。
- `selected8_power.csv`：17 个支持的配置/格式点，修改 `dynamic_mw` 和 `static_mw`。显示 FP16、MXFP8 E4M3、MXFP4 E2M1，不为不支持的格式填写功耗。

总功耗、面积倍率和功耗倍率每次根据输入重新计算，无需手工维护派生列：

```text
area_over_F = area_um2 / area_um2(1:2:4)
total_mw = dynamic_mw + static_mw
power_over_reference = total_mw / total_mw(1:2:4, FP16)
```

功耗图的所有倍率共用 F–FP16 基线，不是各精度分别归一化；紫色底部为静态功耗。样式与源图一致。

默认更新 `paper/figures/selected8_area.png`、`selected8_power.png`，仅输出 PNG。派生 CSV、输入 hash 和绘图说明保存在 `paper/data/results/selected8/`，不会覆盖输入。需要试绘时可分别指定：

```bash
python3 plot_area_power.py --area-data selected8_area.csv --power-data selected8_power.csv \
  --output-dir /tmp/select8/figures --results-dir /tmp/select8/results
```

脚本从自身位置定位默认数据，与运行目录无关。依赖为 Python 3、NumPy、Matplotlib，沿用 `paper/requirements.txt`。迁移输入来自原 DAC2027 目录中的 selected8 导出，来源与原始 hash 见 `sources.json`。自行修改数据不等于新的硬件测量；正文数值和结论需另行同步。
