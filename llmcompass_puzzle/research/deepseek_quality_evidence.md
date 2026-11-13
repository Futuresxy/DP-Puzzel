# 低精度质量证据与适用边界

核查日期：2026-11-13。配套机器可读数据：[literature_deepseek.json](literature_deepseek.json)。所有条目均为 `literature_prior`，不能使本项目方案的质量状态变为 `passed`。未找到同一个 DeepSeek V4/V4.1 checkpoint、相同迁移范围和协议下，BF16/MXFP8/MXFP4/NVFP4/HiF4 五格式完整对照；也未找到可直接绑定本地四档迁移方案的困惑度实测。

## 直接相关的 DeepSeek 证据

| 模型/研究 | 对照指标（基线→量化，百分数） | 范围与边界 |
|---|---|---|
| NVIDIA DeepSeek-V4-Flash-NVFP4 | GPQA 89.4→89.1；AA-LCR 65.8→65.5；τ²-Telecom 94.3→94.2；SciCode 48.1→48.1；IFBench 78.8→79.5 | 卡片称 `Baseline (ours)`，没有基线精度/SHA；不能改写成 BF16 对照。ModelOpt V4 recipe 为 routed experts W4A4，其他模块保留原格式。 |
| NVIDIA DeepSeek-V4.1-Flash-NVFP4 当前版 | GPQA 91.035→90.783；AA-LCR 78.563→79.562；SciCode 54.401→53.994；IFBench 76.667→77.867；MMMU-Pro 74.046→74.566；Terminal-Bench 2.1 81.60→81.88 | 源模型已经混合精度、expert 权重 MXFP4。候选同时改 routed experts 为 NVFP4 W4A4 和 Engram FP8→MXFP4，不能把质量差归因于 A4 一项。 |
| HiFloat4 论文，DeepSeek-V3.1 671B | 十任务均值：BF16 85.44、NVFP4 84.81、NVFP4+PTS 85.24、HiF4 86.42；MMLU 84.86→84.31/84.72/84.77；Math500 75.00→74.00/78.20/80.20 | MLA/MoE/FFN linear 的权重和激活转换，排除 MoE gating；AISBench、vLLM、64×910B。不是 V4 专家局部迁移，未给 checkpoint SHA；均值提升不能证明所有任务不退化。 |

来源：[NVIDIA V4 卡片](https://huggingface.co/nvidia/DeepSeek-V4-Flash-NVFP4)，[NVIDIA V4.1 卡片](https://huggingface.co/nvidia/DeepSeek-V4.1-Flash-NVFP4)，[HiFloat4 原论文 Table V / §IV-C](https://arxiv.org/html/2602.11287v1)。精度差的单位是**百分点**，不是相对百分比。表格为原始报道，未在本项目重测。

V4.1 卡片明确 source revision 为 `dba1be0a40aa45a94ad051997016db3960a90277`，与本地 pinned `314113f8a7dadb388215396ba5fbee2c610a04d6` 不同。其早期候选 `3431dde3247c13b5957f682b1e3c6fcae2566079` 保留 FP8 Engram；本轮无法取得该固定版本的历史评测表，因此不将当前表回填为旧版成绩。

## W4A4 已有实现，不能被原始 W4A8 路径否定

[ModelOpt 的 DeepSeek V4 recipe](https://github.com/NVIDIA/Model-Optimizer/blob/1318c296fca258880834d159c98bc01ff45f1776/examples/deepseek/README.md)明确将 routed experts 的权重和激活转为 NVFP4 W4A4；导出 `weight_scale`、`weight_scale_2`、`input_scale`。`--cast_mxfp4_to_nvfp4` 可保持专家权重的解码值，但输入激活仍需校准。权重无损不等于端到端输出无损。

V4.1 卡片记录：旧 checkpoint 在 SGLang commit `da64c5cbb8cf6bfd39be19da43573fdfd484c43a` 上自动选择 `flashinfer_trtllm_routed`。这是 SGLang 使用 TRT-LLM routed kernel 的路径，不应自动写成独立 TensorRT-LLM 服务已完成同一质量验证。当前 MXFP4 Engram 版由支持对应补丁的 vLLM 评测，SGLang 尚未验证该 Engram 格式。原始 DeepSeek W4A8、部署 NVFP4 W4A4 应是 DSE 中两个明确的 execution profile。

## 同协议跨格式先验：Qwen3-8B

[HiFloat 综合评测 Table 3](https://arxiv.org/html/2602.12635v1)提供相同 RTN 方法下的比较，PPL 上下文为 2048；任务由 LM Evaluation Harness 零样本评测：

| 格式 | 范围 | WikiText-2 PPL↓ | C4 PPL↓ | MMLU↑ | Math500↑ |
|---|---|---:|---:|---:|---:|
| BF16 | 基线 | 9.72 | 15.43 | 73.0% | 78.4% |
| MXFP8 | W8A8 | 9.76 | 15.48 | 72.7% | 79.6% |
| MXFP4 | W4A4 | 11.21 | 18.13 | 65.2% | 72.0% |
| NVFP4 | W4A4 | 10.16 | 16.24 | 70.6% | 78.6% |
| HiF4 | W4A4 | 10.30 | 16.55 | 70.5% | 76.0% |

同一论文中 MXFP4 改用 SmoothQuant/SVDQuant 后，WikiText-2 PPL 为 10.90/10.58。SVDQuant 使用 rank16 分支；其质量收益必须连同额外运算和存储成本建模，不能只换质量分数。此表不是 DeepSeek 质量预测器，亦未给完整 checkpoint/数据集 revision。

## 可以形成的系统研究问题

1. **格式和算法必须共同选择。** “4 bit”不定义质量；缩放、组大小、校准与执行路径都影响结果。最优 Tensor 配比可能因允许的量化 recipe 不同而改变。
2. **保持权重不变，单独研究激活 A8→A4。** V4 已有 MXFP4 expert 权重；lossless cast 可帮助隔离权重变化，但需固定 Engram、KV、router、runtime 和评测协议，才能归因激活迁移的成本/收益。
3. **不能用平均成绩掩盖任务约束。** V3.1 的 HiF4 十任务均值高于 BF16，MMLU 仍低 0.09 pp。DSE 应逐项满足用户指标，再在可行集合内比较延迟、功耗、面积。

建议画两张关联图：第一张横轴质量阈值、纵轴延迟，颜色为 Tensor 配比、标记为量化 recipe；第二张按迁移方案画延迟分解（matrix/vector/quantization/memory）。当前文献只能提供先验带或参考点，未经匹配实测的本地方案标 `unknown`，不能放入“质量达标最优”曲线。

## 数据接口边界

每个实际评测应固定模型与 tokenizer revision、完整精度计划（W/A/KV/累加、模块 scope、格式/组大小/舍入）、算法与校准数据、runtime/kernel、任务数据 revision、prompt/thinking/sampling/max token、随机种子及原始结果 hash。质量绑定整个迁移计划；不得将不同论文的逐层或逐格式损失相加。`quality.py` 的准入证据必须另外产生；本文 JSON 不填 `quality_key`，也不设任何默认达标阈值。
