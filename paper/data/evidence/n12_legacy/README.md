# 旧 PETile 的 N12 面积与功耗

`petile17_area.csv` 按原图顺序收录从 F（1:2:4）到 F+3L（1:8:16）的 17 个配比。面积取自各配比 DC 的 `report/area_detailed.rpt`，保留六位小数。除 F+½E（1:2:6）来自 `PETileFP4Half_N12PPA_1018181343`，其余 16 项来自 `PETile20_Precision_0928174706`。每项与原图 N12 标签的舍入值一致。

两批均采用 N12 TT、0.7 V、85 °C、1.41 GHz 目标频率、Base + LVT 和时钟门控。面积为映射标准单元面积。报告路径相对于上游 `Quant_LLM_Chip_Codesign`，文件指纹见 `petile17_sources.json`。

`petile17_power.csv` 保存同网表的 51 个历史功耗点，覆盖 BF16、MXFP8 E4M3、MXFP4 E2M1。原测量使用 `batch512_ai_load` 的 512 条样本循环，预热 64 拍后统计 1024 拍，以门级 VCD 和 OpenSTA 估算综合后活动功耗。审计状态为 `PASS_WITH_CLOCK_WINDOW_BOUNDARY`。功耗表供追溯使用，等面积延迟分析的硬件输入是 N12 面积和各模式吞吐。

可从上游本地检出重新导入：

```bash
python3.11 paper/scripts/import_petile17_n12.py --source /path/to/Quant_LLM_Chip_Codesign
```
