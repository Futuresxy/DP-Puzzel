# 多精度点积相关工作的比较口径

2026-11-10 核验。比较对象为 Ten-Four、MPICC、MXDOTP（用户所述 MXDOT）、FPnew 和 TransDot。先比较原生格式、点积/累加语义与共享结构，再列原文报告的工况和效率。本表用于组织论文论证，不把异工艺数据作为同条件排名。

| 工作与固定来源 | 支持范围及运算边界 | 原文 PPA 或效率 | 与本项目比较时的边界 |
|---|---|---|---|
| [Ten-Four，arXiv v2](https://arxiv.org/html/2512.00053v2) | TF32、FP16、BF16、FP8/BF8、INT8/4，FP32/INT32 累加，MX 支持；共享浮点/整数点积 | 表 II：8 元素配置、ASAP7 预测库、TT 0.7 V/25°C，面积 1959.86 µm²、功耗 6.28 mW、Fmax 1.571 GHz | 原文格式表未列浮点 FP4，INT4 不能替代 MXFP4；预测 7 nm 与本项目商业 N12 不同。作者网页摘要与 v2 的频率/效率表述有差异，本文固定 v2，不跨版本拼数 |
| [MPICC，ASP-DAC 2025 作者报告](https://www.aspdac.com/aspdac2025/archive/pdf/4A-4.pdf)；[论文 DOI](https://doi.org/10.1145/3658617.3697641) | FP8/FP6/FP4、INT4、LOG4 的异构操作数组合，报告 18 种组合；FP12 通过多步低精度分解仿真；Variable-SR 累加 | 第 25 页：TSMC 28 nm、TT 0.9 V/25°C，DC/PrimeTime PX。第 30 页报告相对所选对照 FP8 面效/能效 1.17×/1.19×、FP4 4.69×/3.64× | 原生 H 支持、多步 FP12 emulation 和本项目每拍原生 H16 分开。报告中的效率增益不能转述成相对 DP-Puzzle；完整面积/功耗及具体比较列仍需从论文表格核对，不从图片猜数 |
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
