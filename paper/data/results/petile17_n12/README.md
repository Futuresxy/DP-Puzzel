# 旧 PETile 17 配比的等面积延迟分析

实验使用 N12 综合面积，并以 DC 目标频率 1.41 GHz 和原生 MAC/cycle 计算峰值吞吐。沿用论文的固定外围面积模型。1:2:4 基准部署 36 核，每核配置 16×16 PETile，计算阵列占基准核面积的 30%，得到 405.566 mm² 的模型预算。整数部署在相同预算内向下取整，可部署 22 至 36 核。每种精度按对应吞吐独占服务，计算时间为各精度 FLOP 数除以各自池化吞吐之和。[N12 综合面积](../../evidence/n12_legacy/petile17_area.csv)

区域边界由两种配比的等延迟直线求交。整数部署下 14 种配比拥有非零最优区域，1:2:4 的区域占 35.96%。连续部署和整数部署的全部 17 项区域比例见 [LaTeX 区域表](../../../tables/petile17_region_table.tex)。这些比例是归一化三角域内的几何占比。

[三角图](../../../figures/petile17_n12_prefill_time.pdf) 叠加 V4-Flash、V4-Pro、V4.1-Flash 的 W4A8 与 W4A4 路由专家轨迹。每条轨迹从 1K 到 1M，实心点为 1M。42 个点的 FLOP 构成、最优配比和相对 1:2:4 的速度比见 [负载表](prefill_points.csv)，各配比的估计时间见 [逐点评估](prefill_evaluations.csv)。

## 渐进精度迁移

| 步骤 | 在上一步基础上的执行精度变化 |
| --- | --- |
| 0 | 路由专家采用 W4A4，沿用当前 W4A4 映射 |
| 1 | Grouped O-down 从 BF16 转为 FP4，Q-down、Q-up、O-up 和共享专家从 FP8 转为 FP4 |
| 2 | 主 SWA/CSA 的 QK 和 PV 从 BF16 转为 FP8 |
| 3 | 步骤 2 的同一批 QK 和 PV 从 FP8 转为 FP4 |

V4 的局部 SWA 和压缩比 4 的 CSA 纳入迁移，压缩比 128 的 HCA 全局支路保留 BF16。V4.1 纳入局部 SWA 与现有 CED 调度中各压缩比的 CSA2 全局支路。模型技术报告及固定输入的指纹见 [迁移记录](precision_migration_manifest.json)。

| 1M 冷启动 prefill | 步骤 0 → 1 → 2 → 3 最优配比 | 步骤 3 FP4 FLOP 占比 | 步骤 3 时间 / 步骤 0 时间 |
| --- | --- | ---: | ---: |
| DeepSeek-V4-Flash | 1:4:12 → 1:2:12 → 1:2:12 → 1:2:12 | 86.36% | 0.692 |
| DeepSeek-V4-Pro | 1:4:8 → 1:2:12 → 1:2:12 → 1:2:12 | 82.88% | 0.638 |
| DeepSeek-V4.1-Flash | 1:6:12 → 1:4:16 → 1:8:16 → 1:4:16 | 96.73% | 0.319 |

在 21 个模型和上下文组合中，步骤 2 的最优配比有 11 个为 1:8:16。步骤 3 将同一批注意力 FLOP 转入 E 后，14 个组合选择 1:4:16。

[局部放大图](../../../figures/petile17_precision_migration.pdf) 使用与主图相同的最优区域颜色。H 占比沿水平网格读数，E 占比沿斜网格投影到底边。空心点表示前六种上下文，实心点和箭头表示 1M 的四步迁移。[LaTeX 迁移表](../../../tables/petile17_precision_migration_table.tex) 列出 1M 的 H/Q/E 占比和时间比。[84 个点](precision_migration_points.csv) 与 [17 配比的逐点评估](precision_migration_evaluations.csv) 保留七种上下文的数据。

迁移仅重分配算子 FLOP 的精度，算子形状、有效工作量、调度和三类以外的 FP32 工作量守恒。结果是对低精度可用性的假设分析，时间指有效 GEMM 的计算服务时间。模型精度、量化转换、数据搬运、利用率和整模型延迟尚待执行验证。

运行 `make -C paper petile17 PYTHON=python3.11` 可从已保存的面积证据复算表格和两张图。
