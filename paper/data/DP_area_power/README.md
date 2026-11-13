# DP 面积与功耗数据及绘图

## 九种完整 DP 配比（2026-11-12）

从 `paper/data/DP_area_power/dp_latest_area_power_20261112.csv` 绘制论文用矢量 PDF。该文件与仓库中的硬件汇总 CSV 内容一致，可用任一路径重绘。输入 SHA-256 为 `f8ca1f225055086db60a0b1a568ebb5c702c41259c198a4efb53adeb647d6006`。[硬件汇总 CSV](../../../hw/data/dp_latest_area_power_20261112.csv)

```bash
python3.11 paper/data/DP_area_power/plot_latest6_area_power.py \
  --combined-csv paper/data/DP_area_power/dp_latest_area_power_20261112.csv
```

合图按 CSV 顺序绘制 9 种配置和 27 个实测功耗点，排除 `dp_top_e64` 和 `dp_top_q32e64`。每行共用一个 H:Q:E 配比标签，左侧柱长为归一化面积，右侧柱长为工具报告的总功耗（mW）。`1:2:4` 行标注原始面积（µm²）和三种精度的实测功耗（mW），其余行标注相对 `1:2:4` 的倍率，功耗按同精度比较。[面积与功耗合图](../../figures/dp_ratio_area_power.pdf)

在上述命令末尾加 `--separate` 可重绘独立图。独立功耗图沿用 `dp_top` 的 BF16 功耗作为统一倍率基准。[独立面积图](../../figures/dp_ratio_area.pdf) · [独立功耗图](../../figures/dp_ratio_power.pdf)

## 当前论文四配比视图（2026-11-11）

中文 DSE 稿使用完整 H/Q/E 候选 1:2:4、1:2:6、1:2:8、1:4:8，输入仍为下面六 DP 批次的 CSV，不新增硬件测量。

```bash
python3 paper/data/DP_area_power/plot_latest6_area_power.py --scope ratios
# 或 make -C paper cost-figures PYTHON=/path/to/python
```

输出 `figures/ratio4_area.png`、`ratio4_power.png` 及 `ratio4_plot_manifest.json`；派生数值保存到本目录 `ratio4_costs.csv`。面积相对基线。功耗沿用 `latest6_power.png` 的画法：柱高和柱顶为实测总功耗（mW），旁侧竖括号的倍率统一以 **1:2:4 的 BF16 功耗 15.3282642364502 mW** 为分母；仅去掉 0:0:4 和 0:2:4。CSV 中各 `*_power_ratio` 也使用这一共同分母。所有柱均为实际支持且已测量的格式。无参数运行仍保留旧六设计绘图行为。

## 最新六种 DP：2026-11-10 v1.9 比较批次，N12 / 1GHz

`latest6_area.csv` 保存六种架构的综合面积、组合/时序面积、工况、DC run 和冻结 RTL export ID。
`latest6_power.csv` 保存 15 个实测格式点的 Internal、Switching、动态、静态、总功耗、K、pJ/MAC，以及功耗审计和负载验证回执路径/hash。
来源为 [`v19_six_dp_20261110.json`](../../../hw/dc_syn/records/v19_six_dp_20261110.json) 和
[`v19_six_architectures_20261110.json`](../../../hw/power/records/v19_six_architectures_20261110.json)；
`latest6_sources.json` 固定来源文件 SHA-256、负载窗口和工况。

| 图中 H:Q:E 配比 | 架构 | 顶层 |
| --- | --- | --- |
| 0:0:4 | E64 | dp_top_e64 |
| 0:2:4 | Q32E64 | dp_top_q32e64 |
| 1:2:4 | T8H16Q32E64 | dp_top |
| 1:2:6 | T8H16Q32E96 | dp_top_t8h16q32e96 |
| 1:2:8 | T8H16Q32E128 | dp_top_t8h16q32e128 |
| 1:4:8 | T8H16Q64E128 | dp_top_t8h16q64e128_opt |

配比为 H/Q/E 原生 MAC/cycle 除以 16；共享单元的不同模式不能同时相加。
功耗图横轴为六种 **H:Q:E 配比**，每组按 BF16、MXFP8 E4M3、MXFP4 E2M1 顺序画支持的精度。
各组分别为 1、2、3、3、3、3 根柱，组宽为柱数加 0.9 单位间隔，支持精度较少的组更窄。
每根柱只展示工具报告的 **total power**，无静态/动态堆叠；未测或不支持的组合不填零。
面积倍率以 `dp_top` 为基准；所有功耗倍率统一以 `dp_top / BF16` 为基准。
CSV 保留原始报告精度，面积与总功耗四舍五入到三位小数后与用户提供的最新表格一致；功耗柱顶显示三位小数。
总功耗保留工具原值，动态=Internal+Switching，静态=Leakage；分项和与总值的校验容差为 0.0005 mW。

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

测量条件：N12 TT / 0.7V / 85°C、1GHz、L8/II=1、ICG 开启；dp_top 为 v1.8 修复基线，三个混合顶层和 Q32E64 为 v1.9，E64 保持原设计。
Qwen3-8B 第 0 层 MLP down_proj 同源 1024 笔输入，发射索引 256..767 的 512ns 窗口；VCS 原生门级 SAIF + Power Compiler。
本次索引中的 15 点均已重新进行冻结 RTL/门级重放、原生 SAIF 和 Power Compiler；E64 仅复用原网表，活动和功耗重新采集。
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
