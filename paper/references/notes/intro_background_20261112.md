# 引言与背景的论证、来源和待补结果（2026-11-12）

本记录对应中文 `sections/01_introduction.tex` 和 `02_background.tex`。本轮按作者指定主线重组，不改第三至第五章的实验数据快照；英文稿和结论未同步。

## 改写前的问题与处理

- 引言仍描述四配比及单一负载选择，改为九种硬件候选、面积/计算建模与双视角 DSE。贡献按研究内容陈述，尚未执行的收益不写成结果。
- 工业配比在引言和背景重复出现，具体产品和数值集中到背景。候选九配比的详细列表继续只在第三章出现。
- 原背景对 related work 的区别过于笼统。分别说明多精度算术、格式/质量/成本协同、系统映射；限定研究缺口为固定格式集合下的配比、核心部署及混合精度负载联动，不宣称不存在量化或软硬件协同研究。
- 阵列组织先于格式细节，区分 GEMM K、原生 K、指令尺寸及互斥模式峰值。微缩放公式保留原语义，补齐相同分组边界的前提与 NVFP4 张量尺度的处理边界。
- 增加迁移场景的语义：精度改变工作量类别、存储量与执行路径，不自动减少有效乘加次数；质量代价由外部证据提供，未知不视为零。

## 核验来源与可支持的论断

| 来源 | 本轮核验内容与采用边界 |
| --- | --- |
| [DeepSeek-V4 v1 §5.2.1](https://arxiv.org/html/2606.19348v1#S5.SS2.SSS1) | MoE 权重 MXFP4；CSA 索引器 QK 在 FP4 中缓存、加载和相乘。引言不由此推导所有专家 GEMM 都原生 W4A4；V4.1 的详细映射沿用第四章声明的目标/参考区别。 |
| [MX-Like v1 §§3–4](https://arxiv.org/html/2610.26083v1) | 共享尺度、权重/激活格式搜索，专用数据通路模板、SNAX 集成，以及困惑度与面积/功耗分析。承认已有质量与硬件成本协同；不把其质量数值直接用于 DeepSeek。 |
| [Ten-Four v3 §§II–III](https://arxiv.org/html/2512.00053v3) | DP 二维阵列、浮点/整数后端复用、MX 支持与稀疏通道门控。背景及功能表统一引用 v3；没有浮点 FP4 支持不能用 INT4 替代。未改异工艺 PPA 比较数值。 |
| [OCP MX v1.0 §§5–6](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf) | MXFP8/6/4 的 E8M0 组尺度与一般点积定义，内部精度和运算顺序由实现规定。 |
| [NVIDIA NVFP4 原始说明](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/) | 16 元素 E4M3 组尺度及额外张量级 FP32 尺度；正文与图注说明后者不能被省略。 |
| [HiFloat4 v2 §II](https://arxiv.org/html/2602.11287v2) | 64 元素 E6M2 组尺度与 8/4 元素微指数；原元素字段图保留。 |
| [LLMCompass 作者仓库](https://github.com/PrincetonUniversity/LLMCompass/blob/main/README.md) | 正式 ISCA 2024 标题、作者与引文；工作提供推理性能、映射及面积建模。新 BibTeX 采用作者提供的元数据。本文未声称已完成 LLMCompass/SCALE-Sim 集成。 |

Crafton 等 DAC 2025 与其他既有工作沿用已核验书目；本轮 DOI 页面读取失败，仅保留“格式与 MAC 架构 Pareto 探索”的题名范围描述，不新增其具体收益或质量结论。

## 工业规格审计

- [NVIDIA HGX](https://www.nvidia.com/en-us/data-center/hgx/)：八 GPU 的 B200/B300 H/Q 数据为 sparse，按官网脚注除 2 后再除 8；FP4 使用 dense 列再除 8。因此得到 2.25/4.5/9 与 2.25/4.5/13.5 PFLOP/s。
- 同页单 Rubin GPU：稠密 FP16/BF16=4、FP8/FP6 training=17.5、NVFP4 training=35。归一化为 **1:4.375:8.75**，不再标成近似 1:4:8；不使用 sparse NVFP4 inference=50。
- [MI355X 原厂规格](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/product-briefs/amd-instinct-mi355x-gpu-brochure.pdf) 与 [MI455X 原厂规格](https://www.amd.com/content/dam/amd/en/documents/products/accelerators/instinct/amd-instinct-mi455x_brochure.pdf)：保留既有 dense 数值及原厂表格舍入，约为 1:2:4 和 1:4:8。
- [Ascend 950 白皮书](https://public-download.obs.cn-east-2.myhuaweicloud.com/ascend/%E6%98%87%E8%85%BE950%20NPU%E6%9E%B6%E6%9E%84%E7%99%BD%E7%9A%AE%E4%B9%A6.pdf) 表 3-1：950PR 高规格档 BF16/FP16=432、FP8/MXFP8/HiF8=865、MXFP4=1730 TFLOP/s。比值舍入为 1:2:4。
- 既有 [960 路线引用](https://www.huawei.com/cn/news/2026/9/hc-wang-keynote) 未给出支持 1/2/8 PFLOP/s 三档值的原始规格。暂撤下该行；不从超节点总算力或媒体转述推导单芯片三档比值。原 BibTeX 条目保留供历史稿查阅。研究候选 1:2:8 不受影响，也不再依赖该商业举例。

## 引言结果占位的补齐条件

1. 成本规律：九候选相同工况的有效面积/动态/静态/总功耗齐备；区分活动模式和非活动扩展资源，报告吞吐增长与成本增长的关系。
2. 部署收益：声明 baseline、面积预算、阵列/带宽约束与频率，再填写模型 GEMM 延迟、功耗及能耗收益范围，不用 DP 能耗冒充整芯片能耗。
3. 关键 insight：从实际九配比优势区域或真实模型迁移轨迹提炼，不能先指定哪种配比最优再选择实验。
4. 质量约束：使用适用的模型、数据集、量化方法和基线；未知质量仅做未验证场景，不称精度保持或可部署结论。

正文结果占位可在 PDF 中看到。全文定稿前还需压缩篇幅，并统一摘要、结论和英文稿。
