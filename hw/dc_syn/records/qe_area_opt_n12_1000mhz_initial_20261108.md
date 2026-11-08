# QE 首轮 RTL 面积优化：N12 / 1GHz

代码检查点：CModel `2aa89c4`，RTL `db31759`。功能证据见 [v1.7.3 验证](../../../test/results/qe-area-opt-v1.7.3.md)。

原始基线和原 QE 为保留的历史综合；核验各自冻结快照、原验证回执及原报告，未伪装成当前源码的新门禁。优化版本使用本轮完整回归与新快照。比较程序核对工艺/库、PVT、工具、参数和最终约束一致。

| 设计 | 面积 µm² | 相对基础 DP | setup slack ps | hold slack ps | 综合验收 |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline | 16929.31 | +0.00% | 0.000894 | 1.063913 | PASS |
| reference | 30580.90 | +80.64% | 0.038147 | 1.051381 | PASS |
| optimized | 28184.85 | +66.49% | 0.001192 | -7.489979 | FAIL |

相对原 QE 减少 2396.05 µm²（7.84%）。+65% 面积上限为 27933.37 µm²；剩余差距 251.48 µm²。目标达成还要求全部时序/电气/VT 验收通过。

## 面积分解

| 模块/分类 | 原 QE µm² | 优化 QE µm² | 减少 µm² |
| --- | ---: | ---: | ---: |
| base_groups | 15410.55 | 14817.45 | 593.10 |
| qe_groups | 10240.01 | 9383.33 | 856.68 |
| global_alignment | 3356.87 | 2550.51 | 806.36 |
| qe_unpack | 2453.23 | 1872.91 | 580.31 |
| qe_local_alignment | 2779.40 | 2681.71 | 97.69 |
| qe_product_bank | 854.62 | 822.18 | 32.44 |
| qe_lane_tree | 714.90 | 681.28 | 33.62 |
| qe_sequential | 2960.69 | 2714.00 | 246.69 |

base_groups、qe_groups、global_alignment 互不重叠；qe_unpack/local_alignment/product_bank/lane_tree 是 qe_groups 内部层级，qe_sequential 是其全部本地时序单元面积之和。这些内部/交叉分类不能再次与组面积相加。映射尺寸变化及后端修复均计入总面积，差额不全等于被删除的 RTL 逻辑。

## 优化版各捕获级 setup

| 捕获级 | 最差 slack ps | 起点 | 终点 |
| --- | ---: | --- | --- |
| S1 | 0.055790 | `in_a_datatype[0]` | `u_core/g_group_2__g_base_u_group_unit/g_lane_1__u_lane/u_lane_unpack/u_operand_b/g_atom_1__ff_s0_s1_classes_ff_storage_out_q_reg_2_` |
| S2 | 0.006795 | `u_core/g_group_0__g_base_u_group_unit/g_lane_0__u_lane/ff_s0_s1_type_s1_ff_storage_out_q_reg_2_` | `u_core/g_group_0__g_base_u_group_unit/g_lane_0__u_lane/ff_s1_s2_products_ff_storage_out_q_reg_43_` |
| S3 | 0.001550 | `u_core/g_group_3__g_base_u_group_unit/g_lane_0__u_lane/ff_s1_s2_products_ff_storage_out_q_reg_24_` | `u_core/g_group_3__g_base_u_group_unit/g_lane_0__u_lane/ff_s2_s3_leaves_ff_storage_out_q_reg_21_` |
| S4 | 0.001192 | `u_core/g_group_0__g_base_u_group_unit/g_lane_1__u_lane/ff_s2_s3_leaves_ff_storage_out_q_reg_90_` | `u_core/g_group_0__g_base_u_group_unit/g_lane_1__u_lane/ff_s3_s4_out_sop_ff_storage_out_q_reg_28_` |
| S5 | 0.040054 | `u_core/g_group_0__g_base_u_group_unit/g_lane_0__u_lane/ff_s3_s4_out_sop_ff_storage_out_q_reg_1_` | `u_core/g_group_0__g_base_u_group_unit/ff_s4_s5_out_z_ff_storage_out_q_reg_1_` |
| S6 | 0.106215 | `u_core/ff_s4_s5_c_datatype_ff_storage_out_q_reg_0_` | `u_core/ff_s5_s6_leaves_ff_storage_out_q_reg_152_` |
| S7 | 0.013828 | `u_core/ff_s5_s6_extension_ff_storage_out_q_reg_0_` | `u_core/ff_s6_s7_sum_ff_storage_out_q_reg_42_` |
| S8 | 0.075340 | `u_core/ff_s6_s7_sum_ff_storage_out_q_reg_31_` | `u_core/ff_s7_s8_out_d_ff_storage_out_q_reg_20_` |

## 工况与来源

TSMC CLN12FFCLL BWP6T16P96CPD，120a；TT/0.7V/85°C，base+LVT 上限20%，DC X-2025.06，ZeroWireload。时间ns、面积µm²。K16/LOCAL28/GLOBAL40，L8/II=1；1ns、setup/hold uncertainty 0.1/0.03ns、IO max/min 0.2/0ns、输出负载0.01pF。

使用 dp-mixed-1000mhz-incremental.json，真实 ICG 开启，时序驱动、最多两次增量优化，无显式面积恢复，仅展开 DFF 包装；不使用 false path/multicycle/retiming。若存在修复，JSON 保存源 run 与策略，最终约束不变。门控覆盖率不代表活动功耗；本轮未运行功耗。

| 设计 | run | export | ICG | 门控寄存器 |
| --- | --- | --- | ---: | ---: |
| baseline | [dc_dp_top_11080044](../runs/dc_dp_top_11080044/REPORT.md) | `DP_verilog_094a23e8843f8ee1` | 76 | 98.65% |
| reference | [dc_dp_top_t8h16q64e128_11080147](../runs/dc_dp_top_t8h16q64e128_11080147/REPORT.md) | `DP_verilog_t8h16q64e128_2ffd38fa6ecd68c2` | 144 | 98.67% |
| optimized | [dc_dp_top_t8h16q64e128_opt_11080736](../runs/dc_dp_top_t8h16q64e128_opt_11080736/REPORT.md) | `DP_verilog_t8h16q64e128_opt_e2fd4e3328a69a69` | 136 | 98.64% |

原始报告、网表和 DDC 保留在本地 runs；这里只提交精简证据。指定 TT corner 的预布局正 slack 不等于布局布线后裕量或多 corner 签核。

复现：

```sh
python3.11 hw/dc_syn/scripts/compare_qe_area.py --baseline-run dc_dp_top_11080044 --reference-run dc_dp_top_t8h16q64e128_11080147 --optimized-run dc_dp_top_t8h16q64e128_opt_11080736 --record qe_area_opt_n12_1000mhz_initial_20261108
```
