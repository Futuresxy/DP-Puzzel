# DeepSeek 四个累积精度方案与芯片配比

[单张矢量图](../../../../../paper/figures/dse_staged_precision_selection.pdf) · [图中数据](figure_cells.csv) · [逐步算子变更](step_moves.csv) · [绘图来源](figure_manifest.json) · [复算命令](../../../../dse/README.md#precision-migration--chip-selection)

| 方案 | 相对上一步新增的精度变化 |
|---|---|
| **Base** | 路由专家保留 W4A8 路径，权重在本地边界前展开，DP 以双侧 MXFP8 计算。Grouped O-down 与 SWA/CSA QK、PV 为 BF16，共享专家和指定投影为 MXFP8。 |
| **Step 1 · O-down + experts** | Grouped O-down（`o_group`）由 BF16 到 MXFP4。路由与共享专家的 `gate/up/down` 由双侧 MXFP8 执行迁到双侧 MXFP4。 |
| **Step 2 · + projections** | `q_down`、`q_up`、`o_final`（O-up）、窗口 KV 投影（V4 的 `window_kv`、V4.1 的 `swa_kv`）由 MXFP8 到 MXFP4。 |
| **Step 3 · + attention** | SWA 和 CSA 的 QK、PV 由 BF16 到 MXFP8。 |

全部方案固定 GEMM 形状、路由与 useful MAC，累加保持 FP32。V4 HCA、Indexer、V4.1 Global-KV projection 保持基线映射。独立 FP32 GEMM 的量化和迁移属于另一组实验。图上方显示这四步的逐精度 MAC 占比，下面的格子分别显示无 DP 功率上限与 150 W 上限时最快的芯片配比。星号表示次优者的时间差小于 1%。

## 比较结果

两代模型均使用 batch 1、2,048-token prefill，V4 走全量 prefill，V4.1 走简化 CED。固定核心池面积预算、1 GHz 和每 SM 四个 `16×4` 阵列。四方案 × 九配比 × 两模型 × 六档每 SM 本地读带宽 × 三种 DP 功率条件（无上限、150 W、250 W），共 **1,296 次评价，144 个配比比较组**。带宽和功率都是解析场景参数。

| 每 SM 4 TB/s，无 DP 上限 | Base | Step 1 | Step 2 | Step 3 |
|---|---:|---:|---:|---:|
| V4 最快配比 | 1:4:4 | 1:2:6* | 1:2:8 | 1:2:8* |
| V4 GEMM 时间（ms） | 210.99 | 134.06 | 104.09 | 93.16 |
| V4.1 最快配比 | 1:4:4 | 1:2:6 | 1:2:8* | 1:2:12 |
| V4.1 GEMM 时间（ms） | 131.26 | 85.94 | 68.67 | 58.46 |
| V4.1 MXFP4 MAC 占比 | 0.08% | 69.22% | 92.10% | 92.10% |

- **Step 1 已释放主要收益。** 允许随方案重新选芯片时，V4.1 在 4 TB/s 的 GEMM 时间比 Base 少 **45.33 ms**。对应最优配比从 Q 较宽的 `1:4:4` 换到 E 增配的 `1:2:6`。这个差值衡量整步迁移的收益，三个算子组的贡献需用单独消融判断。
- **Step 3 可以在 FP4 占比不变的情况下换芯片。** V4.1 的 SWA/CSA 从 BF16 迁到 MXFP8，减轻 H 模式负担后，模型从 `1:2:8` 改选 `1:2:12`。该方案的次优芯片只慢 **1.01%**，需要用真实供数和转换验证排序。
- **带宽与功率会改变迁移对应的硬件收益。** 在 0.5 和 1 TB/s，四方案对两代模型都选 `1:2:4`。V4.1 Step 3 在 4 TB/s 无上限时选 `1:2:12`，加上 150 W DP 上限后改选 `1:2:8`。

## 质量与转换约束

精度方案的可用性需要完整模型的外部质量证据。当前没有这些证据，因此本次质量筛选表为空。比较时用相同 checkpoint、校准数据、量化器版本、评测集和推理设置，对 Base 与每个完整累积方案测 PPL 和目标任务指标。Step 3 还应覆盖长上下文检索或推理。指标允许下降多少由应用给定。评测记录以 `plan_id` 绑定，并同时保存模型与量化器版本。

GEMM 时间从输入已按目标格式就绪开始。离线权重量化、校准和打包是部署成本。在线激活量化、scale 计算、重打包、上游 W4A8 权重展开及实际发生的 KV 重编码，属于运行时成本。比较时使用相对上一步的**净增量**，例如迁移后省掉的权重展开应从新增开销中扣除。若存在重叠，采用实际暴露在关键路径上的时间。

| V4.1 每 SM 4 TB/s，无 DP 上限 | Step 1 | Step 2 | Step 3 |
|---|---:|---:|---:|
| 新方案最快芯片（用于同芯片比较） | 1:2:6 | 1:2:8 | 1:2:12 |
| 固定该芯片的在线转换预算（ms） | 59.31 | 18.41 | 10.29 |
| 上一步与本步各自选最快芯片的预算（ms） | 45.33 | 17.26 | 10.22 |

预算为上一步减本步的模型 GEMM 时间。若新增在线关键路径时间超过预算，该步失去时间收益。两个预算都基于当前的预格式化输入、单缓冲和串行 I/O 场景。模型使用的本地供数口径、A/B 驻留和 ping-pong 的处理见 [面积模型](../../../../area_model/README.md#建模架构与带宽边界) 和 [计算模型](../../../../compute_model/README.md#建模架构与周期)。

## LaTeX caption

```latex
\caption{Precision mix and latency-minimizing BF16:MXFP8:MXFP4 compute ratios for four cumulative plans at batch 1 and 2,048-token DeepSeek prefill. The bars show useful GEMM MAC shares. Each cell selects the fastest of nine profiles under a fixed area budget, local read bandwidth per SM, and DP power condition. The first step moves Grouped O-down and routed/shared experts to MXFP4. The second also moves Q-down, Q-up, O-up, and window KV projections to MXFP4. The third also moves SWA/CSA QK and PV to MXFP8. The outlined row uses 4~TB/s per SM. An asterisk marks a runner-up within 1\% of the minimum modeled latency. Inputs are preformatted and quantization quality is unevaluated.}
```
