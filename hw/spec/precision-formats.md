# 目标精度与数值语义

目标族为 BF16/FP16、MXFP8/6、MXFP4/NVFP4/HiF4。本页汇总格式来源及待核验的数值语义；当前硬件组织以[六种 PE 设计](six-pe-design.md)为准，编码、配对和解包行为见[格式配对](config/FormatCompat.md)与[原子解码](Utils/DecodePrimitives.md)。已实现迁移通路不代表已完成对外部格式规范的完整一致性验证。

| 格式 | 需要独立定义的内容 |
| --- | --- |
| BF16、FP16 | 输入/输出/累加编码、融合或分步运算、舍入、溢出、特殊值 |
| MXFP8、MXFP6、MXFP4 | 元素编码变体、共享缩放格式与 block shape、缩放路径、累加与转换 |
| NVFP4 | 元素与分层缩放、block 粒度、缩放存储/运算及转换成本 |
| HiF4 | 用户指定 arXiv:2602.11287v2；S1P2 元素、E6M2 K64 主 scale 及 K8/K4 微指数；转换算法的中间舍入需单独定义 |

OCP MX 规范定义了 8/6/4 位 microscaling 格式；项目后续应固定规范版本和编码变体。[OCP MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)

NVIDIA 的 NVFP4 文档描述 E2M1 元素、每 16 元素共享的 E4M3 缩放及张量级 FP32 缩放，因而不能把元素的 4 位当成全部存储和计算成本。[NVIDIA Transformer Engine NVFP4](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/nvfp4/nvfp4.html)

这些来源用于建立格式定义，不证明本项目已通过硬件一致性验收。HiF4 依据用户提供的 [论文 v2](https://arxiv.org/html/2602.11287v2) 定义；当前 [AI 数据量化](../test/data/README.md) 使用 FP64 直接转换，不声称逐位模拟论文 BF16 reciprocal 指令的中间舍入。

每个 FormatSpec 还须定义 scale 的轴与布局、量化边界、尾 block、累加顺序、舍入位置、bit-exact/误差判据、允许的转换与必要质量证据。公开标准未覆盖的实现选择由项目规格明确记录。
