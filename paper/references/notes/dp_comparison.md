# 多精度点积相关工作的比较口径

2026-11-10 核验。比较对象为 Ten-Four、MPICC、MXDOTP（用户所述 MXDOT）、FPnew 和 TransDot。先比较原生格式、点积/累加语义与共享结构，再列原文报告的工况和效率。本表用于组织论文论证，不把异工艺数据作为同条件排名。

| 工作与固定来源 | 支持范围及运算边界 | 原文 PPA 或效率 | 与本项目比较时的边界 |
|---|---|---|---|
| [Ten-Four，arXiv v2](https://arxiv.org/html/2512.00053v2) | TF32、FP16、BF16、FP8/BF8、INT8/4，FP32/INT32 累加，MX 支持；共享浮点/整数点积 | 表 II：8 元素配置、ASAP7 预测库、TT 0.7 V/25°C，面积 1959.86 µm²、功耗 6.28 mW、Fmax 1.571 GHz | 原文格式表未列浮点 FP4，INT4 不能替代 MXFP4；预测 7 nm 与本项目商业 N12 不同。作者网页摘要与 v2 的频率/效率表述有差异，本文固定 v2，不跨版本拼数 |
| [MPICC，ASP-DAC 2025 作者报告](https://www.aspdac.com/aspdac2025/archive/pdf/4A-4.pdf)；[论文 DOI](https://doi.org/10.1145/3658617.3697641) | FP8/FP6/FP4、INT4、LOG4 的异构操作数组合，报告 18 种组合；FP12 通过多步低精度分解仿真；Variable-SR 累加 | 第 25 页：TSMC 28 nm、TT 0.9 V/25°C，DC/PrimeTime PX。第 30 页报告相对所选对照 FP8 面效/能效 1.17×/1.19×、FP4 4.69×/3.64× | 原生 H 支持、多步 FP12 emulation 和本项目每拍原生 H16 分开。报告中的效率增益不能转述成相对 DP-Puzzle；绝对面积和逐精度效率依据用户提供的清晰原表补入，来源与换算见下方双表修订记录 |
| [MXDOTP，arXiv v1](https://arxiv.org/html/2505.13159v1) | 原生 MXFP8 E4M3/E5M2；8 元素点积进入 FP32，II=1；SSRs 提供尺度和向量 | GF 12 nm；表 III 单元面积 0.00315 mm²，0.8 V、1.09 GHz，17.4 GFLOPS、2035 GFLOPS/W。八核 cluster 为 0.59 mm²（4.89 MGE），TT 0.8 V/25°C、1 GHz 下 102 GFLOPS、356 GFLOPS/W | 是 FP8 原生缩放点积与处理器集成，不等同于完整 H/Q/E 共享 DP。cluster 面积/能效含处理器及存储，不能直接填进单 DP 成本列；其 FP64–FP8 FPU 范围也不能当作 MXDOTP 原生范围 |
| [FPnew，arXiv v1](https://arxiv.org/abs/2007.01530v1) | 可配置 FP64/FP32/FP16/BF16/FP8，标量和 SIMD、多格式运算；原论文不是原生 H/Q/E 多项融合点积单元 | GF 22FDX 实硅；跨 0.45–1.2 V 测量，报告 178 GFLOPS/W（FP64）到 2.95 TFLOPS/W（8 bit） | 标量/SIMD FMA 与 FP32 累加 dot product 的每周期输出数量不同；效率区间不能当成同电压、同频率下的格式对比 |
| [TransDot，arXiv v1](https://arxiv.org/html/2605.07245v1) | FP32 标量及低精度 SIMD，FP16/FP8/FP4 点积长度 2/4/8，FP32 累加；可重构乘法与移位 | 商业 12 nm；表 II 布局后 TT、0.8 V、1 GHz，三种 DPA 能耗分别为 1.80/0.84/0.41 pJ/FLOP；相对 FPnew 的 FP16/FP8 DPA 面效平均 1.46×/2.92× | 尽管标题提 FPGA AI engines，正文评价包含 ASIC 综合及布局后结果。FP4 元素支持不自动等于 MX/NV/HiF4 的完整尺度合同；本项目不能省略尺度成本后宣称同功能优胜 |

五项来源都已有可核查入口；表中缺少的绝对面积、功耗或格式条件保持未填。后续若建立复现基线，应固定源码 commit、数值合同、原生 K、流水、库、PVT 和负载，再比较同能力面效与能效。

## 本项目的定位

现有工作已经覆盖统一解码、乘法复用、共享移位、融合点积、随机舍入及缩放点积集成。DP-Puzzle 不将这些单独写成首次提出的技术。本文重点是把**共享基础 DP、E/QE 专用扩展、同峰值 K/N 实现与负载配比选择**连成一条可测量的设计链，并研究低精度增配在面积、带宽和功耗约束下的收益范围。

本项目支持 TF32、BF16/FP16、MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3、MXFP4、NVFP4、HiF4 和 INT8；同一请求 A/B 同格式，不能宣称具有 MPICC 的全部异构 A/B 组合能力。输出 RNE 前存在有限窗口 RTZ，不能以“FP32 输出”暗示无限精度点积或与任意 GPU 完全逐位一致。

## 统一指标

面效使用 `K_f ν/A_DP`（MAC/s/mm²）；能耗使用 `P_f/(K_f ν)`（J/MAC），能效是其倒数。若原文用 FLOP/s，一次浮点 MAC 按 2 FLOP 换算。表中一并记录原生 K、II、延迟、是否包含 scale/C/输出舍入、累加精度、面积层次和功耗活动来源。仿真、综合、布局后与实硅分栏，不能用单一节点缩放系数消除差异。

本项目六架构表征见[当前批次](../../../hw/power/records/v19_six_architectures_20261110.md)。基线面积 0.016165122154 mm²，在 1 GHz、II=1 下 H/Q/E 吞吐为 16/32/64 GMAC/s；对应 BF16、MXFP8 E4M3、MXFP4 的总功耗为 15.328264/16.001999/11.196534 mW。它是综合后、CTS/布线前、Qwen3-8B MLP 活动结果，不能直接与上表实硅或布局后能效做公平优胜排名。


## 双表修订与新增核验（2026-11-10）

正文拆为 [格式/功能矩阵](../../tables/related_features.tex) 和 [逐工作 PPA 表](../../tables/related_ppa.tex)。前者区分元素精度、原生多项点积和尺度处理；勾叉仅指引用的具体配置，不代表开放源码未来可配置的所有范围。未能确认的 MPICC 原生 MX 尺度、MXDOTP/TransDot 随机舍入以破折号保留。MPICC 的 FP12 仿真不计入原生 FP16；FPnew 的整数转换不计入原生 INT8/4 乘加。

- FPnew 改用 [原文表 IV 的标称条件](https://arxiv.org/html/2007.01530v1#S5.T4)：22FDX、0.8 V、923 MHz、完整 FPU 0.049 mm²。SIMD FP16/BF16/FP8 的原文性能为 7.42/7.42/14.83 GFLOP/s，能效为 497.67/581.96/1244.78 GFLOP/s/W。面效分别由性能除以 0.049 得到 151.43/151.43/302.65 GFLOP/s/mm²；不再将跨电压的最高能效填作同一工况。
- MPICC 的绝对数字来自用户提供的论文比较表截图（This Work 列）：28 nm、0.9 V、1.43 GHz、2295 µm²；FP8/FP12仿真/FP4 能效 1948/865.1/5931 GFLOP/s/W，面效 1246/415.4/4985 GFLOP/s/mm²。[作者报告](https://www.aspdac.com/aspdac2025/archive/pdf/4A-4.pdf) 第 25 页确认工艺/PVT/综合及功耗工具，第 11、14、23 页说明格式和 FP12 仿真，第 30 页是性能比较。用户截图为本轮新增绝对数值的直接依据；未用其他工作的数据填入 MPICC 列。
- MXDOTP 使用 [原文表 III](https://arxiv.org/html/2505.13159v1#S4.T3) 的独立单元结果，17.4/0.00315 = 5523.81 GFLOP/s/mm²；原文明确该结果为布局后。不能混入八核 cluster 数字。
- TransDot 使用 [原文表 I/II](https://arxiv.org/html/2605.07245v1) 的明确格式与点积能耗。FP16/FP8/FP4 的 1.80/0.84/0.41 pJ/FLOP 以 1000/E 换算为 555.56/1190.48/2439.02 GFLOP/s/W。100×100 µm 的版图边框不等于可直接比较的标准单元面积，因此面积和面效仍留空。
- Ten-Four 的 [表 II](https://arxiv.org/html/2512.00053v2#S3.T2) 区分 1.5 GHz 综合目标与 1.571 GHz Fmax；6.28 mW 缺少逐格式活动条件，不推导逐精度效率。
- 本项目用当前基线面积与三个兼容精度的总功耗换算，BF16/MXFP8/MXFP4 能效为 2087.65/3999.50/11432.11 GFLOP/s/W，面效为 1979.57/3959.14/7918.28 GFLOP/s/mm²。未测 FP16 功耗不由 BF16 替代填表。

图形排版遵从用户要求：单栏 figure，LaTeX subfloat 管理子图标题/编号，完整说明放在 caption；图内只保留数据标记和必要图例。架构图仍由作者补齐，不自动生成。

MPICC 原表截图来源指纹：用户附件 `codex-clipboard-91872e90-c763-4d88-884c-9716b7bc383c.png`，SHA-256 `2ecfa221603dda5de58c1fcd56ae1c5e35bd843c3c04860c8b10f1122014011d`。截图仅用于核对数值和排版形式，不作为论文插图；未复制附件至论文资源目录。


## 第五章精简与建模口径（2026-11-10）

- 格式表移至第二章相关工作，单栏列示 TF32/FP16/BF16、MXFP8/6/4、INT8、NVFP4、HiF4 与配比组合；移除 LOG4、INT4、SR。MX 列的三角标记表示元素运算已报告、完整 MX 缩放尚未建立，不将 FP8/6/4 元素支持改写为 MX 支持。
- 配比组合特指共享 DP 与低精度专用构件的组合式增配。其他工作的破折号表示本文所查来源未报告这一设计方式，不等同于不能实现，也不否认其格式或 SIMD 可配置性。再次核对 Ten-Four v2、MXDOTP v1、FPnew v1、TransDot v1 的上述固定原文入口；MPICC 沿用已核验作者报告与用户截图。
- PPA 表保留原有工艺、测量层次和累加边界；将 GFLOP/s/W、GFLOP/s/mm² 统一除以 1000，改为 TFLOP/s/W、TFLOP/s/mm²。只保留重叠的原生精度，删除 FP12 emulation 效率行；FP16 功耗仍不由 BF16 代填。每个工作单元格内列出格式及其数值。
- 六 DP 图直接使用 `figures/latest6_area.png`、`latest6_power.png`；基线分布使用 `figures/v19_six/v19_dp_top_{area,power}_functions.png`。图形未重绘。功能功耗为逐单元归类之和，与工具总量的末位舍入可略有差异；PPA 与 K/N 计算使用工具报告总量。
- K/N 成本由 `paper/data/kn_comparison/calculate.py` 从已有 CSV 生成，输出 CSV/JSON 和 `tables/kn_costs.tex`。统一按基线 DP 数归一化；1:2:6 对应整数部署仍为两个基线加一个 E64，对比两个扩展 DP。
- 按用户指定，N 中不支持当前模式的附加 DP 使用理想 power-gating 假设：动态、泄漏均为零，不计电源开关、隔离、唤醒和保持开销。物理 DP 面积仍计入。模型只累加 DP 面积和活动功耗，不包含阵列存储、互连或其他逻辑。该零功耗是假设，非新测量；不用于推断已实现 power gating。
- 同精度、同峰值下新增单元活动时，K 的面积低 0.653%--2.402%，活动功耗低 2.020%--3.972%；H 模式下 K 功耗反而高 2.015%--3.686%，E-only 扩展的 Q 模式也高 2.203%--3.862%。独立 E64 与内部 E 构件的流水和规约差异仍保留为比较边界。
- 带宽模型以稳态行列复用、完整缩放块线性扩展和相同 C/D 交换间隔为前提，比较所选存储接口的 bit/s。`B_N-B_K=f(r-1)m(2nc/tau-V)`；`2nc/tau>V` 时 K 较小，反之 N 较小。N 的累加状态每上下文为 `rmnc` bit，K 为 `mnc` bit；不将接口压力误作完整 GEMM 的最终输出总量。
