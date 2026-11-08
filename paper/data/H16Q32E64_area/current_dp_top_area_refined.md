# dp_top 八类面积拆分：符号独立、控制合并

2026-11-08（Asia/Shanghai）。本次沿用同一份已验收 `dp_top`、N12 TT/1 GHz
综合网表，不改 RTL、不重新综合。数据选择/旁路与控制/共享逻辑合并为
**Logic control & shared logic（逻辑控制及共享逻辑）**。该类约 10.92%，不简写为 Other。

## 当前结果

| 类别 | 组合逻辑 µm² | 寄存器 µm² | ICG µm² | 合计 µm² | 占比 |
|---|---:|---:|---:|---:|---:|
| 数据解包与分类 | 2568.462 | 945.893 | 0 | 3514.356 | 19.76% |
| 尾数与 scale 乘法 | 3100.004 | 724.931 | 0 | 3824.935 | 21.51% |
| SOP 累加 | 1663.894 | 193.573 | 0 | 1857.466 | 10.45% |
| 指数处理 | 1735.410 | 492.319 | 0 | 2227.728 | 12.53% |
| 幅值移位 | 1419.633 | 0 | 0 | 1419.633 | 7.98% |
| 符号转换 | 1750.671 | 799.728 | 0 | 2550.399 | 14.34% |
| LZD/规格化/舍入 | 405.172 | 39.813 | 0 | 444.985 | 2.50% |
| 逻辑控制及共享逻辑 | 1459.040 | 396.251 | 87.294 | 1942.585 | 10.92% |
| 总计 | 14102.287 | 3592.507 | 87.294 | 17782.088 | 100% |

对应 CSV：`current_dp_top_area_refined.csv`，功能和寄存器细分在
`current_dp_top_area_refined_detail.csv`。各项保留精确加和值，表中显示值取三位小数。

与上一版相比，35.04% 的大“对齐”类别已被拆开：MAX、delta、anchor 回到指数处理；
能够恢复边界的 E pair 求和回到 SOP；符号准备/恢复独立；INT 旁路归逻辑控制。
移位类别当前为 32 个局部 RTZ 核心和 5 个全局双向移位核心。

## 寄存器边界

继续按所保存结果的生产功能归属。局部和全局对齐叶子是在恢复补码之后保存，
所以它们的 payload 寄存器归符号转换；对应 anchor/common exponent 归指数处理。
这使符号类的 14.34% 中包含约 **4.50 个百分点的寄存器**，组合部分约 **9.85%**。
它并非仅指符号位寄存器，更不能解释成纯取负运算器占 14.34%。
幅值移位类的寄存器为零，表示该统计边界处没有独立的幅值流水保存，
不是整个对齐通路不需要寄存器。S5 scale/直通共用的幅值寄存器仍归乘法输出保存。

## 如何从原网表拆分

1. 校验原冻结 RTL、DC 接受记录和映射网表；每个叶单元仅归入一个类别。
2. 使用原模块层级识别乘法器、规约树、MAX、移位核心、LZD 等已有独立边界。
3. 对局部 delta、全局 anchor/净移位量、group anchor 和 scale 指数等，按
   实际输入输出端点回溯父层逻辑锥，切断已有子模块或流水边界。
4. E pair、INT 旁路、最终取幅值等中间信号已被综合改名或融合。先用固定种子的
   1024 组并行布尔样本筛选候选，再用 Z3 检查候选与对应 RTL 数学函数的异或是否
   **不可满足**。随机命中本身不算通过；每个采用的候选均有逐 bit 的等价证明。
   不把恒零/恒一节点当作算术边界。
5. 对 pair 输入处理与求和，结合已证明的求和端点和操作数依赖，把单操作数符号准备
   与同时组合两个操作数的求和逻辑分开；不把 pair 前后全部操作计入加法器。
6. 不重复累加同一物理单元。逻辑锥冲突、无法恢复的混合门留在控制/共享明细；
   不按位数、RTL 行数或经验比例分配面积。

这是一种可复现的**网表归属口径**，不是对综合融合后的每个数学运算给出唯一物理成本。
共享的库单元不能人为拆成若干面积碎片。

## 仍无法唯一拆开的部分

- E pair 的部分中间 sum/abs 节点被融合消除，不能全部恢复为独立切点；已识别的 pair
  求和锥面积为 **284.074 µm²（1.60%）**，归 SOP。未能唯一拆出的余下逻辑保留在
  `Unresolved mixed alignment logic`，不宣称该 1.60% 是全部 E pair 的精确独立成本。
- group 取幅值与 scale/旁路选择、C 的 INT 取幅值与浮点解码存在融合；没有足够的
  独立节点时，不能仅凭语义把整段输入锥都算作符号转换。
- 控制/共享中的 `Unresolved mixed alignment logic` 约 **3.10%**，
  `Inline shared control and unattributed combinational logic` 约 **4.15%**。
  这些仍包含共享计算和格式选择，不能把整个 10.92% 解读成纯 valid/FSM 控制开销。
- 幅值移位的 7.98% 是独立移位核心成本；格式落位中融合的动态选择仍在控制/共享。

因此本次结果比原模块大类更能区分指数、求和与符号处理；上述混合逻辑仍应在论文
描述和优化判断中保留边界说明，不能隐藏到一个看似很小的 Other 中。

## 功耗与复现

将同一份新逐单元归属用于原 BF16、MXFP8 E4M3、MXFP4 SAIF 功耗报告，得到
`current_dp_top_power_refined.csv`。没有重新产生活动或测量功耗，三个模式的总功耗
均保持原逐叶汇总值。旧七类 CSV/图保留用于对照。

```bash
# 当前机器临时依赖：z3-solver 位于 /tmp/dp-cone-deps
PYTHONPATH=/tmp/dp-cone-deps python3.11 hw/power/scripts/reclassify_functional_area.py \
  --run hw/power/runs/dp_top_cones_1108_232611

PYTHONPATH=/tmp/dp-functional-plot-deps python3.11 \
  paper/data/H16Q32E64_area/plot_area.py --refined
```

输出图：`paper/figures/current_dp_top_area_refined_share.png` 与
`paper/figures/current_dp_top_power_refined_share.png`。

补充来源在 `current_dp_top_area_refined_sources.json`。本地 run 保存逐单元归属、
布尔证明切点和商业库函数表，库内容不提交。`export_functional_cones.tcl` 读取
`DP_POWER_CONFIG` 指定的原功耗配置，恢复 DDC 后只导出函数和节点，不执行 compile。
新环境需安装 Python 的 `z3-solver`（本轮 5.3.3.0）与绘图依赖 matplotlib。
