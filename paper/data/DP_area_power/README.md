# Select8 面积与功耗图

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
