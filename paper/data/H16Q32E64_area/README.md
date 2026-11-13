# 六种 DP 的面积占比

[area.csv](area.csv) 每种架构七行，共 42 行，单位为 µm²。环图用分项面积之和计算总面积与占比。

[三种 DP 的面积横向比较](../../figures/v19_six/v19_dp_area_comparison.png)统一用 `dp_top` 的七类面积之和作为分母。每条柱保留原七类及配色，右侧是整颗 DP 相对基线的面积。从仓库根目录运行：

```sh
python3 paper/data/H16Q32E64_area/plot_area_comparison.py
```

| 架构 | 面积图 |
|---|---|
| T8H16Q32E64 | [面积图](../../figures/v19_six/v19_dp_top_area_functions.png) |
| T8H16Q32E96 | [面积图](../../figures/v19_six/v19_dp_top_t8h16q32e96_area_functions.png) |
| T8H16Q32E128 | [面积图](../../figures/v19_six/v19_dp_top_t8h16q32e128_area_functions.png) |
| T8H16Q64E128 | [面积图](../../figures/v19_six/v19_dp_top_t8h16q64e128_opt_area_functions.png) |
| E64 | [面积图](../../figures/v19_six/v19_dp_top_e64_area_functions.png) |
| Q32E64 | [面积图](../../figures/v19_six/v19_dp_top_q32e64_area_functions.png) |

安装 Matplotlib 后，在仓库根目录运行 `make -C paper dp-share-figures`。面积使用本目录的 `plot_area.py`，总功耗使用 `../H16Q32E64_power/plot_power.py`，两者共用样式，输出 600 dpi PNG。每张图记录对应输入表的 SHA-256 和实际字体。六个已有类别沿用参考图配色，`Norm & round` 用浅橙色。字体优先选 Times New Roman，本批使用本机的 Nimbus Roman。[参考图](../../figures/H16Q32E64_area_pie.png) · [总功耗数据](../H16Q32E64_power/README.md)

分项源自 2026-11-10 验收的逐单元归集。历史分类、明细与对账保存在提交 `0582ed5`。未来批次可用 `plot_area.py --refresh-from <已审核分类报表目录>` 刷新两张表并重绘面积图；再运行 `make -C paper dp-share-figures` 更新全部图。该目录需包含分类器输出的 `seven_functions_area.csv` 和 `seven_functions_power.csv`。[原始归类与对账](https://github.com/Futuresxy/DP-Puzzel/blob/0582ed58e556e33e13c59bfec8fed787c1f77343/paper/data/H16Q32E64_area/v19_six/README.md) · [DC 面积汇总](../../../hw/dc_syn/records/v19_six_dp_20261110.md)
