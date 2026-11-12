# 扩展 DP 的 N12 / 1 GHz 综合验收

工况：N12 BWP6T16P96CPD 120a、TT/0.7V/85°C、base+LVT≤20%、ICG、L8/II=1，LOCAL28/GLOBAL40。
所有所选运行的库、工具版本、时钟/IO、电气及编译预算均逐项一致；setup/hold、电气及VT全部通过。层级展开策略按架构记录，面积差异包含该策略影响。
结果为 ZeroWireload、理想时钟下的综合后证据，不是 CTS/布线后签核。极小正裕量只表示本工况通过。

| 架构 | 面积 µm² | setup ps | hold ps | ICG | 门控寄存器 |
| --- | ---: | ---: | ---: | ---: | ---: |
| T8H16Q64E64 | 24015.384704 | 0.000119 | 0.024334 | 201 | 8555/8689 |
| T8H16Q32E192 | 26620.010691 | 0.006080 | 0.442848 | 237 | 9127/9297 |
| T8H16Q32E256 | 29692.809442 | 0.011206 | 0.052661 | 281 | 10896/11110 |
| T8H16Q96E192 | 38234.345695 | 0.004649 | 0.083819 | 349 | 13727/13913 |
| T8H16Q128E256 | 46925.549827 | 0.006914 | 1.055464 | 449 | 17652/17890 |

## 捕获级 setup 裕量（ps）

| 架构 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T8H16Q64E64 | 0.096440 | 0.000119 | 0.010848 | 0.034690 | 0.016451 | 0.021935 | 0.135183 | 0.044823 |
| T8H16Q32E192 | 86.343348 | 0.014067 | 0.082850 | 0.077128 | 0.018239 | 0.006080 | 0.076771 | 0.022173 |
| T8H16Q32E256 | 47.365248 | 0.027061 | 0.240207 | 0.680208 | 0.095606 | 0.011206 | 0.120997 | 0.066280 |
| T8H16Q96E192 | 3.968656 | 0.004649 | 0.004649 | 0.054121 | 0.015855 | 0.049114 | 0.149131 | 0.045657 |
| T8H16Q128E256 | 0.192404 | 0.007987 | 0.126004 | 0.006914 | 0.013113 | 0.057697 | 0.026941 | 0.031829 |

每列按捕获寄存器归属统计，不假定路径一定起自相邻前级；起止点见JSON及原始报告。

## 冻结来源

- `T8H16Q64E64`：[dc_dp_top_t8h16q64e64_11121920](../runs/dc_dp_top_t8h16q64e64_11121920/REPORT.md)；RTL `DP_verilog_t8h16q64e64_044cfe1be3f22a8d`；原始验证 `20261112T105255076422Z`。
- `T8H16Q32E192`：[dc_dp_top_t8h16q32e192_11121924](../runs/dc_dp_top_t8h16q32e192_11121924/REPORT.md)；RTL `DP_verilog_t8h16q32e192_b677d181f0a29c7f`；原始验证 `20261112T112212019154Z`。
- `T8H16Q32E256`：[dc_dp_top_t8h16q32e256_11122032](../runs/dc_dp_top_t8h16q32e256_11122032/REPORT.md)；RTL `DP_verilog_t8h16q32e256_87332acf0b331629`；原始验证 `20261112T112213175348Z`。
- `T8H16Q96E192`：[dc_dp_top_t8h16q96e192_11122038](../runs/dc_dp_top_t8h16q96e192_11122038/REPORT.md)；RTL `DP_verilog_t8h16q96e192_1e63c2625d0dd101`；原始验证 `20261112T122236879949Z`。
- `T8H16Q128E256`：[dc_dp_top_t8h16q128e256_11122210](../runs/dc_dp_top_t8h16q128e256_11122210/REPORT.md)；RTL `DP_verilog_t8h16q128e256_f8209095129aa89a`；原始验证 `20261112T122135109358Z`。

## 层级优化策略

- `T8H16Q64E64`：`dp-mixed-l8-1000mhz-incremental`；展开模块：`dp_lib_DFF*`, `dp_dff_*`。
- `T8H16Q32E192`：`dp-mixed-l8-1000mhz-incremental`；展开模块：`dp_lib_DFF*`, `dp_dff_*`。
- `T8H16Q32E256`：`dp-mixed-l8-1000mhz-align-flat-incremental`；展开模块：`dp_lib_DFF*`, `dp_dff_*`, `dp_max_tree*`, `dp_mixed_global_align*`, `dp_bidir_shift*`, `dp_rtz_shift*`, `dp_lane_align*`, `dp_lzd*`, `dp_scale_multiply*`, `dp_exponent_add*`, `dp_fp32_round*`。
- `T8H16Q96E192`：`dp-mixed-l8-1000mhz-incremental`；展开模块：`dp_lib_DFF*`, `dp_dff_*`。
- `T8H16Q128E256`：`dp-mixed-l8-1000mhz-align-flat-incremental`；展开模块：`dp_lib_DFF*`, `dp_dff_*`, `dp_max_tree*`, `dp_mixed_global_align*`, `dp_bidir_shift*`, `dp_rtz_shift*`, `dp_lane_align*`, `dp_lzd*`, `dp_scale_multiply*`, `dp_exponent_add*`, `dp_fp32_round*`。

各run保存原始日志、约束、DDC、网表和SDC；修复使用新run并保持完整来源链。
功耗使用相同网表，但须另经真实负载 RTL/门级重放、原生 SAIF 及活动审计；本表不代表功耗通过。
