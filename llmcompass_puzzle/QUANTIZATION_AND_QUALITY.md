# W4A8/W4A4 实现审查与质量接口

2026-11-13。固定源文件及 SHA-256 见 [quantization_sources.json](../dependencies/quantization_sources.json)。源文件只读审查，不导入远端代码、不下载模型权重。外部研究由两个子 agent 分别核查 DeepSeek/MX/NV 与 HiF4；[DeepSeek 证据](research/deepseek_quality_evidence.md)、[HiF4 证据](research/hif4_quality_evidence.md) 保留模型、范围、指标和缺失项。

## 已有实现与本项目成本路径

**DeepSeek 路由专家 W4A4 已经有公开实现。** 原始模型的 W4A8 参考 kernel 与 NVIDIA 的 NVFP4 W4A4 是不同 execution profile；前者不能否定后者。DSE 研究其配比/系统适配成本，不以“首次让专家运行 W4A4”为贡献。

| 固定代码 | 审查结论 |
|---|---|
| V4-Flash `60d8d707…`，`model.py:linear`、`kernel.py:fp4_gemm_kernel` | W4 存储、A8 输入；W4 在 shared buffer 中展开为 FP8，再作 FP8 GEMM。没有默认向 HBM 写回整个 FP8 权重副本。activation group128，scale dtype 由初始化参数决定，不能只看全局初值断言 FP32 |
| V4.1-Flash `314113f8…`，同名路径 | W4/A8 参考路径，activation group32、E8M0 scale；局部 W4 展开单独计 vector-equivalent 工作 |
| NVIDIA ModelOpt `1318c296…`，DeepSeek V4 recipe | routed expert 的 W/A 转为 NVFP4 W4A4，group16；导出 block scale、per-tensor scale 和 input scale。不是全模型全部算子 FP4 |

固定实现入口：[V4 原始 kernel](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/60d8d70770c6776ff598c94bb586a859a38244f1/inference/kernel.py)、[V4.1 原始 kernel](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/inference/kernel.py)、[ModelOpt recipe](https://github.com/NVIDIA/Model-Optimizer/blob/1318c296fca258880834d159c98bc01ff45f1776/examples/deepseek/README.md)。

`fp4_act_quant` 的存在不意味着所有 expert GEMM 已使用 A4：它还用于 indexer/KV 路径。`inplace=True` 的量化再反量化保留 BF16 存储，也不能算成压缩后的 KV 字节。将原始 A8 quantizer 改成 A4 后，还必须更换 GEMM 输入契约、scale 布局及支持内核。

ModelOpt 的特定 MXFP4→NVFP4 cast 可以保持权重解码值；这不保证新增的激活量化无损。离线校准与在线 block quant 分开计费。

## 在线 A4 成本的控制模型

`system_contract.quantization_work()` 统计每元素 vector 工作、每 block 归约/scale 工作、每 32-bit packed word 打包工作；`moe_system.py` 再用声明过的 vector 服务率和各层流量计算时间。默认系数是情景输入，没有伪装成实测 CUDA 指令或纳秒。实际实现可以使用 SIMD、转换指令或专用单元，因此应校准等效服务率，不把“量化全由普通 FP16 ALU 完成”当事实。

以 BF16 输入的 32 个值、MX group32 为例：

- A8 独立量化：64 B 源读取 + 32 B payload + 1 B scale = 97 B。
- A4 独立量化：64 B 源读取 + 16 B payload + 1 B scale = 81 B。
- 输出表示减少约 48.5%，但该转换的总逻辑流量只减少约 16.5%；amax/scale 工作仍存在。这些字节不一定都经过 HBM。

NVFP4 group16 需要更多 block scale，并有 per-tensor scale；不能直接套用 MX group32 数值。融合省 launch 与中间读取，不把计算成本归零。W4A8 baseline 已有量化，迁移比较是完整新旧执行图之差，不是在免费 A8 基线上另加一次 A4 开销。

## 质量不是位宽的固定损失函数

NVIDIA V4-Flash-NVFP4 的公开卡片报告 GPQA 89.4→89.1%、SciCode 48.1→48.1%；其基线名为 `Baseline (ours)`，不能改标 BF16。V4.1 当前卡片还包含 Engram 迁移，不能将全部差异归因于 routed expert A4。来源、完整表和版本限制见研究文档。本批未运行完整模型质量评测，也未找到与本地所有方案严格匹配的质量数据。

HiF4 的 V3.1 结果、Qwen/LLaMA 的跨格式 PPL 可用于选待测方案，但不能赋给 V4/V4.1。每条文献记录均为 `literature_prior`，没有可直接准入本地候选的质量键。PPL 相对增幅与准确率百分点下降不能互换；平均指标提升不代表每个任务都不退化。

## 可配置接口

`quality_key(model_revision, config_sha256, numerical_plan)` 绑定完整数值计划，包括算子 scope、W/A/KV/累加格式、组大小、舍入、quantizer、校准与数值图。`system_search` 的 `numerical_recipes` 初始为空绑定，因此成本可探索、质量为 unknown。

`assess_quality(key, policy, records)` 要求 policy 中所有指标通过。`configs/quality_policy.json` 的空 requirements 表示 unknown，不是默认无限宽松。用户按实际评测设定要求，例如下列**接口示例，不是本项目已采用阈值或实测结果**：

```json
{
  "mode": "require_matching_measurements",
  "requirements": [{
    "id": "task_accuracy", "metric": "accuracy", "unit": "fraction",
    "dataset": "USER_TASK", "dataset_revision": "PINNED_REVISION",
    "protocol": "PINNED_PROTOCOL_ID", "scope": "full_model",
    "direction": "higher", "degradation_mode": "absolute",
    "max_degradation": 0.005
  }]
}
```

这里 0.005 fraction 表示允许下降 0.5 个百分点。PPL 可使用 `direction=lower`、`degradation_mode=relative`。协议必须说明 tokenizer、样本/上下文、prompt、thinking/sampling、最大输出长度、随机种子以及推理实现；先聚合重复运行，再导入一个唯一记录，不自动挑最好一次。

每个 evidence record 包含 `quality_key`、上述 metric/unit/dataset/revision/protocol/scope、`evidence_kind=measurement`、`reference_value`、`candidate_value`、`artifact` 和 `artifact_sha256`。阈值来自 policy，不能由 record 自行放宽。原始评测文件须存在且 hash 一致；本接口核验身份及声明的分数，不自动复算任意格式的评测日志，导入方负责分数与原始产物的一致性。

缺记录、错模型/方案/协议、artifact 不匹配或文献先验都保持 unknown；任何必需指标失败则 failed；全部满足才 passed。`synthetic_test_only` 只在单元测试显式开启，正常 CLI 不接受。成本最优与质量达标最优始终分表；不能把 unknown 填成零损失。
