# DeepSeek 精度迁移与最优芯片配比

[单张矢量图](../../../../../paper/figures/dse_precision_selection.pdf) · [图中数据](figure_cells.csv) · [绘图来源](figure_manifest.json) · [复算命令](../../../../dse/README.md#precision-migration--chip-selection)

前一轮扫描对路由专家的 W4A8/W4A4 方案比较了全部九种配比，其余迁移方案只比较了三个固定部署。这次在同一面积预算、1 GHz 和 4×16×4 DP/SM 组织下，将 **24 个精度方案与九种芯片配比完整交叉**。V4 用全量 prefill，V4.1 用简化 CED。两者均为 batch 1、2,048 tokens，各扫六个本地读带宽点和三个 DP 功率条件（无上限、150 W、250 W），共 7,776 次评价、864 个配比比较组。

上方堆叠条显示每个方案的 BF16/MXFP8/MXFP4 有用 MAC 占比。下方两组矩阵显示无 DP 功率上限和 150 W 时的最快配比，横轴与上方的迁移方案对齐，纵轴为每 SM 本地读带宽。星号表示次优配比的时延相对最快者高不到 1%，方框标出 4 TB/s 的比较行。250 W 与其余方案可在复算结果的 `selections.csv` 中查到。

| 图中方案 | 相对基线的精度变化 |
|---|---|
| Base | 路由专家走 W4A8，权重在本地边界前展开为 MXFP8 |
| O-down 8 / 4 | 仅将 Grouped O-down 从 BF16 迁到 MXFP8 / MXFP4 |
| Experts 4 | 仅将路由专家改为原生 MXFP4 输入 |
| Both 4 | Grouped O-down 和路由专家均迁到 MXFP4 |
| Aggressive | 在 Both 4 基础上，指定投影和共享 FFN 迁到 MXFP4，SWA/CSA 的 QK/PV 迁到 MXFP8 |

## 读图结论

1. **单独迁移 O-down 可以保留芯片配比。** 在每 SM 4 TB/s、无 DP 功率上限时，O-down 从 BF16 迁到 MXFP8 后，两代模型仍选 `1:4:4`。模型 GEMM 时间分别缩短 **13.8%**（V4）和 **10.3%**（V4.1）。
2. **增加 FP4 工作量时，最优配比可能先缩 Q，再加 E。** V4.1 在同一条件下，基线选 `1:4:4`，只迁专家后 FP4 占比从 **0.1%** 升至 **52.3%**，赢家改为 `1:2:4`。再迁 O-down 后占比到 **60.5%**，模型选 `1:2:6`，但只领先 `1:2:4` **0.50%**。前一步削减了 MXFP8 工作量，适合保留较多独立供数的核心。
3. **供数和功率预算共同影响配比选择。** 在所扫的 0.5 和 1 TB/s 点，两代模型的全部 24 个计划在三个 DP 功率条件下均选 `1:2:4`。V4.1 只迁专家时，4 TB/s 选 `1:2:4`，16 TB/s 选 `1:4:8`。同样在 16 TB/s 加 150 W DP 上限后，赢家变为 `1:2:6`。

这组比较固定有用 MAC、形状和路由。时间从预格式化操作数的本地边界开始，量化质量及新增格式转换成本仍需验证。功率上限约束解析模型中的 DP 并发，图中赢家按模型 GEMM 时间排序。完整数据另列最低 DP 能耗的配比。

## LaTeX caption

```latex
\caption{Precision mix and latency-minimizing BF16:MXFP8:MXFP4 compute ratios for batch-1, 2,048-token DeepSeek prefill. The bars show useful GEMM MAC shares for each operator-specific plan. Each cell selects the fastest of nine DP profiles at a fixed area budget, local read bandwidth per SM, and DP power condition. Base executes routed W4A8 through MXFP8. O-down 8/4 changes Grouped O-down to MXFP8/MXFP4, Experts 4 changes routed experts to MXFP4, and Both 4 combines the two MXFP4 moves. Aggressive also lowers selected projections and shared FFN to MXFP4 and SWA/CSA QK and PV to MXFP8. An asterisk marks a runner-up within 1\% of the minimum modeled latency. The outlined row uses 4~TB/s per SM. The model assumes preformatted local inputs and leaves quantization quality unevaluated.}
```
