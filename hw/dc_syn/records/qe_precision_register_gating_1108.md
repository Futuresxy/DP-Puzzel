# Q32E64 精度寄存器门控综合

N12 BWP6T16P96CPD 120a base+LVT，TT/0.7V/85°C，DC X-2025.06；K16/LOCAL28/GLOBAL40，L8/II=1，1GHz，ICG开启。新旧 technology/constraints 配置完全一致，未新增 false/multicycle path、case analysis 或 retiming。

| 指标 | 原基线 | 精度门控 |
| --- | ---: | ---: |
| 总面积 µm² | 11542.081582 | 11873.120309 |
| 组合面积 µm² | 8494.461031 | 8789.815406 |
| 时序单元面积 µm² | 3047.620551 | 3083.304903 |
| 寄存器数量 | 4511 | 4527 |
| ICG数量 | 68 | 108 |
| 门控寄存器数量 | 4443 | 4459 |
| setup/hold/VT/电气规则 | PASS | PASS |

面积变化 +2.8681%；新最差 setup/hold slack 分别为 0.015497ps/0.170842ps，LVT占 19.61%。这是指定 TT 角的预布局综合，极小正余量不代表多角度布线签核。

- 基线 `dc_dp_top_q32e64_11080855`；新结果 [dc_dp_top_q32e64_11081629](../runs/dc_dp_top_q32e64_11081629/REPORT.md)。
- 新快照 `DP_verilog_q32e64_8fc17d1108154f48`；[功能验证](../../../test/results/qe-precision-register-gating.md)。
- [机器摘要](qe_precision_register_gating_1108.json)。网表/DDC/原始报告保留在本机 run。

除导出标识外，两份冻结源码仅四个 lane/unpack 文件内容不同；生产 compact QE 分支变化集中在 dp_lane_qe、dp_lane_unpack_qe。公共算术与后端源码一致。面积差额包含门控控制/重构与本次映射时序优化，不是 ICG 本体面积的独立测量。
