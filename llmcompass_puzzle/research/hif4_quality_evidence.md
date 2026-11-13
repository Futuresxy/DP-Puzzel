# HiF4 / MXFP4 / NVFP4 质量证据

核查日期：2026-11-13。状态：`literature_prior`；以下是外部作者报告，未在本项目复现，不能直接作为 DeepSeek-V4 / V4.1 或本项目迁移方案的质量验收。机器可读摘要见 [literature_hif4.json](literature_hif4.json)。

## HiF4 定义与 DeepSeek 实例

[HiFloat 官方推理白皮书](https://hifloat.gccorg.com/docs/en/hifloat4/white_paper/hifloat4_format_for_language_model_inference.html) 的格式章节与 Table 5 提供一手依据。HiF4 每 64 个值包含 256-bit S1P2 载荷、8-bit E6M2 scale、8-bit 每 8 值微指数和 16-bit 每 4 值微指数，合计 4.5 bit/value。它与 `ratio_dse/formats.py` 的存储布局吻合，但 **S1P2 不等于 MX/NVFP4 的 E2M1**；布局吻合也不代表舍入、特殊值及量化器已经逐位验证一致。

Table 5，DeepSeek-V3.1 671B：

| A/W 格式与 recipe | 十任务均分 % | MMLU % | Math500 % |
| --- | ---: | ---: | ---: |
| BF16 | 85.44 | 84.86 | 75.00 |
| NVFP4 direct-cast | 84.81 | 84.31 | 74.00 |
| NVFP4 + per-tensor scaling | 85.24 | 84.72 | 78.20 |
| HiF4 direct-cast | 86.42 | 84.77 | 80.20 |

平台为 64 Ascend 910B、vLLM、AISBench；W/A 转换覆盖 MLA_linear、MoE_linear（不含 gating）及 FFN_linear。均分包含 ARC-C/E、BoolQ、HellaSwag、PIQA、WinoGrande、GSM8K、MMLU、Math500、CMMLU。均分提高仍伴随 MMLU 下降，因此不能用均分替代逐任务阈值；作者报告的改善也不能证明普遍优于 BF16。这里没有 PPL 或同条件 MXFP8 数据。量化需要分组归约、scale/微指数生成和转换打包，应单独刻画在线成本。

## MXFP4 的推理与 PPL 证据

[M²XFP，ASPLOS 2026 作者论文](https://chenzhangsjtu.github.io/files/2026-ASPLOS-M2XFP.pdf)，§6.1、Table 3/4/6：PyTorch 数值模拟、lm-evaluation-harness，MXFP4 group32、NVFP4 group16；M²XFP 是另一个格式，**不是 HiF4**。

| 模型 / 指标 | FP16 | MXFP4 | NVFP4 |
| --- | ---: | ---: | ---: |
| LLaMA2-7B / WikiText-v2 PPL | 5.47 | 7.15 | 5.81 |
| LLaMA3-8B / WikiText-v2 PPL | 6.14 | 8.30 | 7.18 |
| DeepSeek-R1-Distill-Qwen-1.5B / 五任务均分 % | 49.03 | 36.91 | 未报告 |
| DeepSeek-R1-Distill-Qwen-7B / 五任务均分 % | 63.30 | 56.00 | 未报告 |

推理任务为 AIME-90、MATH-500、GSM8K、GPQA、LiveCodeBench；1.5B 均分下降为 **12.12 个百分点**。Table 8 还报告 LLaMA2-7B MXFP4 的 scale 取整方法变化使 PPL 从 7.15（floor）变为 6.21（ceil/RTNE）。因此 format 名称不足以唯一确定质量。FP16 不可标作 BF16；蒸馏 Qwen 不能标作完整 DeepSeek MoE。该文没有提供目标 V4/V4.1 的迁移损失。

## 在系统 DSE 中的使用边界

- 质量索引至少绑定 checkpoint/revision、量化 recipe、权重/激活/KV 格式、层/算子 scope、block/scaling/rounding、校准集、评测协议及运行精度实现。不同训练/PTQ recipe 是不同候选。
- `literature_prior` 可用于设定敏感性区间或挑选待测方案，不能自动变成目标模型的 `validated` 或 `pass`。缺失质量记录为 unknown，不填零损失。
- PPL 相对增幅与准确率百分点下降分别计算；不得相互换算，也不从 activation MSE 直接推导 PPL。跨论文 PPL 必须核查 tokenizer、样本、上下文长度和切分方式。
- 对完整迁移组合做质量门禁，不能默认各层损失线性相加。在线 A4 量化开销独立于离线权重量化/训练成本；融合 norm 也只能免去部分访存与启动，不自动消除归约及转换工作。
- 本次未核实到 DeepSeek-V4/V4.1 同协议 BF16、MXFP8、MXFP4、NVFP4、HiF4 全套结果。目标模型仍需用户实测或严格匹配的公开记录。
