# 六种 DP 的总功耗占比

[power.csv](power.csv) 每种架构七行，共 42 行。三个精度列保存各功能类别的总功耗（动态＋静态，mW）。空值表示架构不支持该精度，图中对应位置显示 `Unsupported`。分项保留逐单元归集的精度，环图中心与百分比均按分项之和计算。

| 架构 | 总功耗图（BF16 / MXFP8 E4M3 / MXFP4 E2M1） |
|---|---|
| T8H16Q32E64 | [总功耗图](../../figures/v19_six/v19_dp_top_power_functions.png) |
| T8H16Q32E96 | [总功耗图](../../figures/v19_six/v19_dp_top_t8h16q32e96_power_functions.png) |
| T8H16Q32E128 | [总功耗图](../../figures/v19_six/v19_dp_top_t8h16q32e128_power_functions.png) |
| T8H16Q64E128 | [总功耗图](../../figures/v19_six/v19_dp_top_t8h16q64e128_opt_power_functions.png) |
| E64 | [总功耗图](../../figures/v19_six/v19_dp_top_e64_power_functions.png) |
| Q32E64 | [总功耗图](../../figures/v19_six/v19_dp_top_q32e64_power_functions.png) |

功耗绘图脚本：[plot_power.py](plot_power.py)。安装 Matplotlib 后，从仓库根目录运行：

```bash
python3 paper/data/H16Q32E64_power/plot_power.py
```

默认读取本目录 `power.csv`，六张功耗图输出到 `paper/figures/v19_six/`。也可以在本目录运行 `python3 plot_power.py`。运行 `make -C paper dp-share-figures` 可同时重绘面积和功耗图。面积图和功耗图共用分类、字体和颜色。[面积图与更新说明](../H16Q32E64_area/README.md)

本批覆盖 15 个兼容精度点，采用 N12 TT、0.7 V、85°C、1 GHz 和 Qwen3-8B MLP 门级 SAIF。完整动态与静态总量及原逐单元归类可分别从验收报告和 Git 历史查阅。[功耗验收报告](../../../hw/power/records/v19_six_architectures_20261110.md) · [原始归类与对账](https://github.com/Futuresxy/DP-Puzzel/blob/0582ed58e556e33e13c59bfec8fed787c1f77343/paper/data/H16Q32E64_area/v19_six/README.md)
