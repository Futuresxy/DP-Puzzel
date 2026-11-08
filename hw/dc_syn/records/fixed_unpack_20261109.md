# 固定格式直接解包：dp_top 同约束综合对照

2026-11-09（Asia/Shanghai）。RTL 基线提交 `36bbbf5`。本批只优化组合解包，
不改变数值格式、S1/S2 流水边界、L8/II=1 或 CModel。功耗未重新测量。

| 项目 | 基线 | 固定格式直接打包 | 减少 |
|---|---:|---:|---:|
| dp_top 总面积（µm²） | 17782.087803 | 16831.217776 | **5.3473%** |
| 全 DP 组合面积（µm²） | 14102.286526 | 13193.220274 | 6.4462% |
| 全 DP 时序单元面积，含 ICG（µm²） | 3679.801277 | 3637.997501 | 1.1360% |
| 8 份 u_lane_unpack 合计（µm²） | 3364.3193 | 2375.4792 | **29.3920%** |
| 8 份 A operand 解包合计（µm²） | 1588.5802 | 1091.6536 | 31.2812% |
| 8 份 B operand 解包合计（µm²） | 1587.9537 | 1091.3217 | 31.2750% |
| 物理 DFF 数 | 5383 | 5319 | 64 |
| ICG 数 | 148 | 148 | 0 |

**统计边界：** `u_lane_unpack` 是相同 RTL 模块边界的 inclusive 面积，包含局部指数
解码、符号/INT8 取幅值、S1 存储与配对分类，不是此前七类功能图中的“Data unpacking”
切片。父/子行是不同观察边界，不能相加。本次不按比例更新旧七类面积图。

解包模块节省 988.8401 µm²，全 DP 净节省 950.8700 µm²；其他模块重新映射合计
增加约 37.9701 µm²，已计入全 DP 结果。不能将局部节省直接等同于整机节省。

## 来源与条件

- 基线 run：`dc_dp_top_11081432`；export `DP_verilog_a32ed7ef4b093ffa`。
- 本次 run：`dc_dp_top_11090056`；export `DP_verilog_ce47b3d5b06c0eca`。
- 两者 technology、constraints、parameters 的解析配置完全相同：K16/28/40，
  TSMC CLN12FFCLL BWP6T16P96CPD 120a、base+LVT、TT 0.7V/85°C，DC X-2025.06。
- 时钟 1ns，clock gating 开启、最小位宽 4，`dp-mixed-1000mhz-incremental.json`；
  相同 IO、uncertainty、负载、层级保留及最多两次增量时序优化，无 retiming。
- 面积依据两次正式 `summary.json` / `reports/area_hierarchy.rpt`，单位 µm²。
  逐实例 CSV 与精简 JSON 为 [CSV](fixed_unpack_20261109.csv)、[JSON](fixed_unpack_20261109.json)。

## 时序与门禁

本次 synthesis_valid、flow_pass 均 true；setup/hold PASS，无电气违例，
LVT nonblackbox 占比 19.40%，满足 20% 配额。时钟、复位、datatype/valid 正常计时，
未添加 false path、multicycle 或 case analysis。

- 全局最差 setup slack：+0.000031829 ns（**+0.031829 ps**），在 S6。
- 全局最差 hold slack：+0.000030205 ns（**+0.030205 ps**）。
- 解包 S1 setup slack：从 +0.000062466 ns 改善为 **+0.041324377 ns（41.324 ps）**。

在当前 TT 综合条件下 1GHz 通过，但全局余量很小；不代表布线后或多 corner 签核。
未重新生成 SAIF/功耗数据，不能从面积下降直接宣称功耗降低。原六架构功耗对照及
catalog 保持原网表来源，本次结果单独保存。

## 收益来源

固定格式在生成期确定字段位置/宽度，直接生成 M16/E10/S4，取消通用可变字段提取
及二次选择打包。NaN/Inf/sNaN 从原始字段同时判定，Q 的补零与 HiF4 的 e1 使用
固定拼接，未删除任一已支持精度。

RTL 的 S1 DFF、精度门控和输出连线与基线逐字节一致，但 DC 自动少保留 **64 个
物理 DFF**。对比 `register_stages.tsv`：全部是 16 份 A/B 解包的 atom0 槽 2/3，
包括 32 个 class_high 和 32 个 signaling。这些槽仅 E 使用，不会产生 Inf/NaN/sNaN；
直接布局使恒零关系明确，工具得以裁剪。没有提前 A/B 特殊摘要，没有改变流水。

逐寄存器差集及重算脚本位于本次 run 的 `analysis/`，原网表/DDC/报告保留在该 run。
功能回归和 659200 笔字段对照见 [验证记录](../../../test/results/dp-fixed-unpack-20261109.md)。
