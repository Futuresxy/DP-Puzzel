# H16Q32E64 面积占比图

修改 `area_data.csv` 后运行 `python3 plot_area.py`，或在 `paper/` 下执行 `make cost-figures`。

脚本读取 `category` 和 `total_um2`：将相同类别的面积相加，再除以整份 CSV 的总面积。环图百分比、中心的完整 DP 面积随数据自动更新。单位为 µm²。其余字段保留原测量的功能块及组成信息，不参与计算；修改它们不会自动改变 `total_um2`。

默认输出 `paper/figures/H16Q32E64_area_pie.png`，仅生成 PNG。类别面积、占比与输入 hash 保存在 `paper/data/results/H16Q32E64_area/`。输入为原 `area_data.csv` 的逐字节复制，来源 hash 见 `sources.json`。

```bash
python3 plot_area.py --data area_data.csv \
  --output /tmp/area-share/H16Q32E64_area_pie.png --results-dir /tmp/area-share/results
```

默认路径相对脚本定位。保留原图的分类顺序、配色、字体和 600 dpi；迁移前后默认生成的 PNG 一致。图名由原来的 `petile_full_area_pie.png` 统一为论文资产名 `H16Q32E64_area_pie.png`。
