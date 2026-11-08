# H16Q32E64 面积占比图

当前推荐查看 **[八类细分结果](current_dp_top_area_refined.md)**：符号转换独立，
数据选择/旁路与控制/共享合并。面积 CSV 为 `current_dp_top_area_refined.csv`，
重绘用 `plot_area.py --refined`。下面保留旧七类和 PETile 历史数据的说明。

修改 `area_data.csv` 后运行 `python3 plot_area.py`，或在 `paper/` 下执行 `make cost-figures`。

脚本读取 `category` 和 `total_um2`：将相同类别的面积相加，再除以整份 CSV 的总面积。环图百分比、中心的完整 DP 面积随数据自动更新。单位为 µm²。其余字段保留原测量的功能块及组成信息，不参与计算；修改它们不会自动改变 `total_um2`。

默认输出 `paper/figures/H16Q32E64_area_pie.png`，仅生成 PNG。类别面积、占比与输入 hash 保存在 `paper/data/results/H16Q32E64_area/`。输入为原 `area_data.csv` 的逐字节复制，来源 hash 见 `sources.json`。

```bash
python3 plot_area.py --data area_data.csv \
  --output /tmp/area-share/H16Q32E64_area_pie.png --results-dir /tmp/area-share/results
```

默认路径相对脚本定位。保留原图的分类顺序、配色、字体和 600 dpi；迁移前后默认生成的 PNG 一致。图名由原来的 `petile_full_area_pie.png` 统一为论文资产名 `H16Q32E64_area_pie.png`。

## 当前 dp_top：功能面积与真实负载功耗

2026-11-08 新增 `current_dp_top_*` 数据，来自当前带精度寄存器门控的
T8H16Q32E64 `dp_top`。**上面的 `area_data.csv` 是旧 PETile 论文数据，不能混用。**
新数据与旧数据、旧图分别保存。

- `current_dp_top_area.csv`：7 类面积与百分比，分组合逻辑、寄存器和 ICG。
- `current_dp_top_power.csv`：BF16、MXFP8 E4M3、MXFP4 E2M1 各 7 类；保存
  internal、switching、dynamic、leakage、total，以及三类功耗各自的占比。
  `register_dynamic_mw` 包含寄存器时钟引脚内部功耗。
- `current_dp_top_{area,power}_detail.csv`：分类下的功能、物理组成明细。
- `current_dp_top_reconciliation.csv`：逐叶单元之和与原验收总报告的差值。
- `current_dp_top_sources.json`：固定快照、DC/功耗 run、条件、报告校验和与分类限制。

### 分类口径

复核见 [功能面积分类审计](current_dp_top_area_audit.md) 和
`current_dp_top_area_audit.csv`：七类统计的总量/层级已核对，但对齐类包含
E pair、指数差和符号/选择等混合逻辑，不能据此比较纯移位器与全部加法器成本。

每个叶单元只归入一类，不叠加父层级面积/功耗。寄存器按所保存的数据归属；同一份
分类用于面积与三种精度功耗，不按精度重新分摊物理面积。下表是**功能边界归集**，
不是从映射门级网表自动恢复每个数学运算的精确成本。

| 类别 | 计入的逻辑和寄存器 |
|---|---|
| Data unpacking | lane 紧凑解包和 S1 bank，scale 解包/S1 保存，C 解包/S5 保存 |
| Mantissa & scale multiplication | 元素乘法 bank（含乘积重构）、S2 乘积及符号/有效旁带、scale 系数乘法和流水、group scale 乘法、S5 幅值寄存器 |
| Exponent arithmetic | 元素指数加法、S2 指数、scale 指数流水、S5 group anchor 寄存器 |
| Alignment & exponent selection | lane/group MAX、局部对齐通路、全局 MAX/delta/双向移位/符号恢复、S3 对齐叶寄存器、anchor/common exponent 及 S6 操作数保存 |
| Addition & accumulation | lane 规约树、group 求和、最终规约树，lane/group/final sum 相关寄存器 |
| LZD, normalization & rounding | group/C/最终 LZD、前导计数保存、最终规格化/舍入/编码和 INT 输出转换、S8 输出寄存器 |
| Others | ICG 单元及其驱动网络、控制/特殊值流水、原始 C 搬运寄存器、未能可靠分开的内联组合逻辑 |

边界说明：

- `dp_lane_align` 内部还包含 E 类 pair 预处理、MUX、符号恢复，整体计入局部对齐通路；
  因此“对齐占 35% 面积”**不是纯 barrel shifter 占 35%**。
- group 中未保留独立层级的 abs、anchor 算术、缩放/旁路选择和共享控制仍列 Others，
  不凭名称猜测 Uxxx 单元的精确用途。Others 的组合部分占总面积约 4.86%，
  其余是已知 ICG、控制寄存器和 C 搬运；详细数值见明细 CSV。
- S5 幅值寄存器同时承载 scale 乘法和旁路结果，归在乘法类；不能将该类在 BF16/MXFP4
  下的全部功耗解释为 scale 乘法器的功耗。
- 物理寄存器的时钟引脚内部功耗计回其功能类；ICG 单元独立列 Others。
  每个单元行已含其驱动网络 switching，不再叠加 net 行或 clock_network 汇总。
- 占比分母为叶单元之和。库面积属性和逐单元功耗打印有精度限制，原验收值另存，
  不把小差值按比例摊入功能块。最大相对差约 0.0055%（switching 分项），未超过
  汇总检查的 0.02% 容差；这不是功耗模型本身的误差界。

### 固定证据与结果范围

使用 `DP_verilog_a32ed7ef4b093ffa`、`dc_dp_top_11081432` 的原 DDC；
K_FP16=16、LOCAL_W=28、GLOBAL_W=40、L8/II=1。N12 TT、0.7 V、85 °C、1 GHz。
原功耗点来自 `power_precision_register_gating_1108/dp_top__*`，Qwen3-8B MLP
工作负载、VCS 原生门级 SAIF、512 ns 活动窗口。输入检查复核冻结验证证据和原功耗
审计产物校验和，补充报告只恢复 DDC、SAIF 和原时钟转换时间，不重新综合。
结果是综合后、布局布线前的功耗，不包含 CTS/SPEF/SDF 后的物理实现开销。

本地补充原始报告与逐单元归属表位于
`hw/power/runs/dp_top_functional_1108_224637/`，由本目录来源清单引用；大报告不提交。
82,502 个叶单元中包含 5,383 个数据/控制寄存器和 148 个 ICG。总面积约
17,782.088 µm²。原验收总功耗与叶单元加和的精确值见 reconciliation CSV。

### 重绘

使用安装了 matplotlib 的 Python 环境，从仓库根目录执行：

```bash
python3.11 paper/data/H16Q32E64_area/plot_area.py --current
```

本机本轮的临时依赖在 `/tmp/dp-functional-plot-deps`，可直接运行：

```bash
PYTHONPATH=/tmp/dp-functional-plot-deps python3.11 \
  paper/data/H16Q32E64_area/plot_area.py --current
```

输出：

- `paper/figures/current_dp_top_area_share.png`
- `paper/figures/current_dp_top_power_share.png`：三行精度，三列动态/漏电/总功耗。

图为 600 dpi PNG，共用相同类别配色；脚本不改动旧图。
绘图输入 hash 和执行清单位于忽略的 `paper/data/results/H16Q32E64_area/`。
重新汇总既有补充报告：

```bash
python3.11 hw/power/scripts/summarize_functional_power.py \
  --run hw/power/runs/dp_top_functional_1108_224637
```

需要重新导出报告时，在新的本地 run 子目录设置 `DP_POWER_CONFIG` 指向对应已验收
功耗点的 `config.tcl`，调用本机 EDA setup 后运行
`dc_shell -f <仓库>/hw/power/scripts/export_functional_power.tcl`。
该入口只报告，不执行 compile。机器、商业库和许可证路径不放入版本控制。
