# 配比驱动的 MoE 系统分析：首批受控结果

状态：**解析模型中的条件性结果；不是实测推理性能、完整 TTFT 或质量达标推荐。** 主问题、输入输出与内部结构见 [MOE_STUDY.md](../../MOE_STUDY.md)，质量审查见 [QUANTIZATION_AND_QUALITY.md](../../QUANTIZATION_AND_QUALITY.md)。本批开始于冻结的结构化资源池，未根据结果任意扩大维度。

运行：`llmcompass_puzzle/runs/moe-system-20261113-v3`。486 个硬件设计，23,328 个工作负载/迁移/融合/功率组合，20,152 个通过当前面积、容量及映射/功率情景检查。九 DP、两模型、256/2048 token、三个专家执行方案、融合开/关、无 cap/250 W 两个情景。主案例为 **V4-Flash、2048 个全 EP 组 token、8 卡 EP、融合量化**。

面积预算约 826.764 mm²，来自上游成本基线；同频 1 GHz。物理/启用 SM、vector、HBM 和 L2 分开记录。功率为显式未校准情景；NVFP4 DP 动态功率用 MXFP4 代理。全部候选质量为 unknown，因此质量推荐为 **0**。

## 三个有明确对照的观察

以下均为主案例的 **NVFP4 routed-expert W4A4、无功率 cap**。shared experts 保持 FP8。精确候选 ID、公式和数值在 [findings.json](findings.json)，阶段证据在 [primary_operator_breakdown.csv](primary_operator_breakdown.csv)。

| 对照 | 子层延迟 | 解释与边界 |
|---|---|---|
| 固定其他资源，`1:2:4 → 1:2:16` | 0.471103 → 0.470961 ms，仅减少 **0.030%** | FP4 峰值增至 4 倍，专家 GEMM 仍由 HBM 服务限制；通信约占 25.9%。该微小差不应被解释为有意义的性能优势，核心观察是收益饱和 |
| 保持 `1:2:4`，系统资源协同 | 0.471103 → 0.371704 ms，减少 **21.10%** | 候选从 128 物理/108 启用 SM、vector 1×、HBM5，变为 96/81 SM、vector 2×、HBM8；L2 保持 40 MiB。更少 SM 配合更强 vector/供数在本情景更有利 |
| 两边都完成系统优化后，`1:2:4 → 1:6:12` | 0.371704 → 0.353076 ms，再减少 **5.01%** | 原始固定基线到最终候选总共减少 25.05%，其中很大部分来自通用系统调优，不能把全部归功于配比 |

第三项还揭示更具体的机制：节省的 18.627 µs 中，**18.240 µs（97.92%）来自仍使用 FP8 的三个 shared-expert GEMM**；路由专家三个 GEMM 只节省 0.387 µs。模型大部分专家已迁到 A4，也不意味着应该只增加 E：剩余 Q 工作和服务瓶颈仍决定增配价值。优化后的通信占比为 34.57%，继续扩 Tensor 的收益会受不变通信限制。

这些观察不是对任意上下文、路由、量化算法或芯片的保证。尤其第三项依赖本批 shared 保持 FP8、顺序子图和通信路径；完整 attention/mHC/Engram 接入后须重新比较。

## 功率、迁移与近似并列

| 专家方案 | 无 cap 的最低成本候选 | 250 W 情景的最低成本候选 |
|---|---|---|
| W4A8 | `1:6:12`，HBM8，0.387465 ms | `1:4:4`，HBM4，0.627092 ms |
| MXFP4 W4A4 | `1:6:12`，HBM8，0.343307 ms | `1:8:16`，HBM5，0.433518 ms |
| NVFP4 W4A4 | `1:6:12`，HBM8，0.353076 ms | `1:8:16`，HBM5，0.447906 ms |

上述候选都使用 96 物理/81 启用 SM、vector 2×、40 MiB L2，但每阶段实际活跃 SM 与供数速率不同。功率情景改变了可用的计算/搬移组合；“装得下”不等于“可以同时开满”。这是条件性示例，**不是实际 250 W 芯片规格推荐**。

对两种 W4A4，未限功率的 `1:4:4/1:4:8/1:6:12`，以及 250 W 下的 `1:4:4/1:6:12/1:8:16` 均在各自最低延迟的 1% 内。当前校准不足，不能声称某一比值稳健胜出。应优先校准区分这些候选的 shared GEMM、vector、HBM 功率，而非围绕第四位小数扩搜。

固定同一硬件进行融合消融，主案例各候选节省约 6.0–8.63 µs，转换工作仍保留；相关 ID 与数值见 [fusion_ablation.csv](fusion_ablation.csv)。这是 launch/访存简化模型的结果，不是已测得 fused kernel 的加速。

更大配比在粗 SM 池中可能因预算迫使 SM 档位下降；这种跳变需要局部细化合法安装档位后才能作为硬件结论。本批不把离散网格造成的排序反转宣传为普遍规律。

## 图与复现

[主图 PDF](../../../paper/figures/llmcompass_moe_ratio_system.pdf) 为四面板“迁移×配比”热图：固定资源/系统优化 × 无 cap/250 W 情景。相同绝对延迟色阶；灰色表示不可行。每个优化单元允许选择不同硬件，因此右侧纵向不是固定完整硬件的迁移比较。真正的固定硬件反向选择保存在原 run 的 `cost_only_selections.csv`。

```bash
bash llmcompass_puzzle/run_system_dse.sh llmcompass_puzzle/runs/my-moe
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.summarize_system \
  --run llmcompass_puzzle/runs/my-moe --output llmcompass_puzzle/runs/my-moe-summary
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.system_findings \
  --summary llmcompass_puzzle/runs/my-moe-summary --output llmcompass_puzzle/runs/my-findings.json
# 绘图环境安装 requirements-figures.txt；绘图依赖不进入仿真虚拟环境
python -m llmcompass_puzzle.system_figure \
  --summary llmcompass_puzzle/runs/my-moe-summary \
  --pdf paper/figures/my-moe.pdf --evidence llmcompass_puzzle/runs/my-figure.json
llmcompass_puzzle/.venv/bin/python -m unittest discover -s llmcompass_puzzle/tests -v
```

精简记录包含受控单元、主案例阶段分解、配对比较、融合消融与双向选择中的 workload→hardware 表；全部候选和全阶段大表保存在被忽略的 run，hash 见 [run_manifest.json](run_manifest.json)。旧 v1 为内部试跑，v2 缺完整 manifest，均不作本报告证据。

## 验证、来源与剩余工作

- [tests.txt](tests.txt)：19 项测试，含命令行相对/外部配置路径、输出完整性、两方向选择和 unknown 质量排除。另对全量有效候选检查面积/容量/功率包络、能量上界，对主图单元检查阶段时间和；见 [evidence.json](evidence.json)。
- 图为单页矢量 PDF、字体嵌入、无嵌入位图；生成数据/代码/PDF hash 见 [figure.json](figure.json)，图注见 [figure_caption.tex](figure_caption.tex)。
- 运行 manifest 自动记录了当时所有模块，包括早期绘图脚本。仿真后仅绘图模块改为纯矢量输出；其旧源码保留在 run 的 `source_snapshots/system_figure.py`，新图以独立 figure manifest 为准。仿真/汇总代码的 hash 均可核验。
- 实测 DP 是 N12 综合后证据，N7 面积/动态功率为工艺代理；量化工作系数、非 DP 功率、局部无冲突供数、缓存/通信调度仍是未校准假设。单元测试不能证明这些数值准确。
- 下一阶段先做 grouped GEMM/量化/带宽与功率的持出校准，再补完整 prefill 图。质量方面先绑定完整 checkpoint/recipe/协议和实测指标，当前公开成绩只作先验，不能把本表变成质量达标建议。
