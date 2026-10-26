# AI 数据采集、量化与软件 dot golden

当前数据已实际生成：两个模型**第一层（索引 0）**，每个 49,152 MAC，合计 **98,304 MAC / 格式**。语料为 WikiText-2 raw test；模型、tokenizer 和数据集版本固定在 [sources.json](sources.json)。本阶段没有人工定向或随机测试向量，没有运行 DUT 仿真或功耗分析。

用户将原中间层方案改为首层以缩小下载。本工具按 safetensors 字节偏移读取必要 tensor/embedding 行，检查 HTTP 206 和 Content-Range，不回退到下载完整分片。实际首次权重读取：Qwen 8,906,240 B，MoE 51,672,776 B，共约 57.8 MiB；本地 range cache 不重复下载。元数据/tokenizer/语料另计。每模型所需权重片段总量预算为 128 MiB；失败重试流量另计，单片段最多尝试 3 次。

## 目录和入口

```text
hw/test/data/
  sources.json                    固定版本、首层采集参数
  fetch.py                        获取配置、tokenizer、数据集；不下载权重分片
  weights.py                      safetensors 按字节读取与片段来源记录
  collect.py                      首层真实输入和权重采集
  formats.py / quantize.py         格式解码、独立量化、16-bit word 打包
  golden.py                       FP64 点积参考与原生 K 索引表
  validate.py / test_formats.py    软件数据一致性检查
  ai-first-layer-summary.json      跟踪的小型结果与 hash 摘要
  cache/                          忽略：权重片段缓存
  artifacts/ai_wikitext2_l0_v1/     忽略：完整数据产物
    raw/{qwen_qproj,moe_downproj}/
    quantized/<source>/<format>/
    golden/<source>/<format>/
```

完整数据保留在当前工作区，尚无远程大产物归档。Git 保存代码、定义与精简摘要；模型权重不提交。Python 依赖版本见 [requirements.txt](requirements.txt)，原始捕获 manifest 另记录实际设备、线程、软件版本和采集代码 hash。

在项目根目录执行（当前已准备的隔离环境为 `.deps/verification-env`）：

```bash
.deps/verification-env/bin/python hw/test/data/fetch.py
.deps/verification-env/bin/python hw/test/data/collect.py
.deps/verification-env/bin/python hw/test/data/quantize.py
.deps/verification-env/bin/python hw/test/data/golden.py
.deps/verification-env/bin/python hw/test/data/validate.py
.deps/verification-env/bin/python -m unittest discover -s hw/test/data -p test_formats.py -v
```

采集、量化和 golden 拒绝覆盖已有输出。复现实验使用新的 `--output`（collect）及相应 `--corpus`（其余入口），验证摘要也可通过 `--summary` 另存。下载缓存默认在 `.deps/`，实际采集/生成结果均在本目录 `artifacts/`。完整参数和来源保留在各级 `manifest.json`。

## 实际采集边界

每个来源为 `A[4,768] × W[16,768]^T → Y[4,16]`，K 从原张量第 0 列开始，64 对齐。

| 来源 | 算子 | 选中 token 位置 | 原始 K |
| --- | --- | --- | --- |
| Qwen2.5-3B | `model.layers.0.self_attn.q_proj` | 32, 106, 180, 255 | 2048 |
| Qwen1.5-MoE-A2.7B | `model.layers.0.mlp.experts.3.down_proj` | 43, 129, 178, 251 | 1408 |

16 个输出通道为 64, 192, …, 1984，Q 投影每个 head 取一个通道。每个模型独立 tokenize 同一份按数据集顺序拼接的原始文本，使用最前 256 tokens；前 32 个位置只提供上下文，不作为样本 token。

Q 激活为官方 RMSNorm 对真实 token embedding 的输出。MoE 使用官方 Transformers 的首层 causal eager attention、残差、RMSNorm 和路由计算；从有至少 4 个候选 token 的专家中按 `(命中数, expert ID)` 排序选择下中位数，再沿该专家真实命中的 token 分层取 4 个。当前选中 expert 3，256 tokens 中有 18 个 token 实际命中。其 down 输入由该专家真实 gate/up 和 SiLU 计算，未混入 router probability。

这是首层目标算子的实际依赖计算，采用 BF16 tensor 运算和官方模块内的 FP32 norm/softmax；未执行后续无关专家、层或完整模型输出。权重、激活保持 BF16 位模式。bias 单独保存，路由结果单独保存；当前 dot 输入不含 bias、路由输出加权或 C。该小样本不能代表所有层、语料或完整模型质量。

`raw/` 的 `a_parent_bf16.npy` 保存整段 Q 激活池或该专家全部命中激活，`b_parent_bf16.npy` 保存该算子完整权重，用于保留 NVFP4 parent amax。`a_bf16.npy` / `b_bf16.npy` 是最终选择的 K768 子块，dtype 为 uint16，其内容是 BF16 原始位模式；同名 `.mem` 供直接读取。shape、token/通道/原 K 坐标、统计及文件 hash 在原始 manifest 中。

## 量化规则

九种编码为 BF16、FP16、MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3、MXFP4、NVFP4、HiF4。每种都独立从上述 BF16 数值生成，不级联转换。先量化被选择的完整原 K 行，再取已对齐的 K768；PE/profile 变化不重新量化。

软件基线为 FP64 算术、RNE、有限值饱和，保留符号零，无额外旋转或校准。此基线不等于对任何厂商完整量化 recipe 的逐位复现。

- MX：每 K32 一个 E8M0，指数为 `floor(log2(block_amax)) - floor(log2(element_max_finite))`，夹到 E8M0 有限范围；零块采用 scale=1。
- NV：一维 K16 正 E4M3 scale。global scale 为完整捕获母张量 `amax/(448×6)` 转 FP32，A/B 独立；block scale 用 RNE 编码 `block_amax/(6×global_scale)`。若 block scale 下溢到零，该块编码为带原符号的零。不采用二维权重缩放。
- HiF：K64 的 E6M2 为 `amax/7` 的 RNE 编码，零块主 scale=1（0xc0）。g1 每 K8 按局部峰值/主 scale 是否 ≥4 选择；g0 每 K4 按局部峰值/(主 scale×2^g1) 是否 ≥2 选择。元素为 S1P2。**使用 FP64 直接计算，不模拟论文 Algorithm 1 中间 BF16 reciprocal/乘法舍入。**

NVFP4 global scale 不送入现有 PE 内部算术；必须区分其局部数值域和原张量数值域。HiF4 使用 `x=(-1)^s×(m/4)×2^(g0+g1)×S`，单层微指数 bit 0 和 1 分别对应乘数 **1 和 2**。

## `.mem` 文件合同

每行一个无符号十六进制存储字，ASCII/LF，无 `0x` 前缀、注释或地址指令。索引 0 在第一行；宽度补足到整 hex 位。文本不涉及字节序；二进制数值是格式原始编码，不是十进制打印值。各目录 manifest 的 `memories` 记录路径、位宽、元素数和 shape。

| 文件 | 每行位宽 | 顺序与用途 |
| --- | --- | --- |
| `a.elements.mem` / `b.elements.mem` | 16 / 8 / 6 / 4 | `[M,K]` / `[N,K]` 行优先，K 连续；FP6 以两位 hex 保存，最高两 bit 为 0 |
| `a.words.mem` / `b.words.mem` | 16 | 符合 PE 的 W16 打包；最早 K 元素在最低 lane |
| `a.scales.mem` / `b.scales.mem` | 8 | 仅 block 格式；每行原 K 的 scale block 按顺序连续保存 |
| `a.g0.mem` / `b.g0.mem` | 1 | 仅 HiF4，每 K4 一 bit，0 或 1 |
| `a.g1.mem` / `b.g1.mem` | 1 | 仅 HiF4，每 K8 一 bit，0 或 1 |
| `a.global_scale.mem` / `b.global_scale.mem` | 32 | 仅 NVFP4，每操作数一个 FP32 原始编码 |

W16 中 BF16/FP16 为一个元素；FP8/FP6 为两个 byte lane，FP6 的 byte 高两 bit 清零；FP4 为四个 nibble。每行 A/B 的 word 数分别为 K、K/2 或 K/4。`elements` 和 `words` 是同一数据的两种视图，验证脚本逐项核对。

当元素索引为 `(r,k)`、每字 L 个元素、scale block 为 B 时：

```text
element address = r*K + k
word address    = r*(K/L) + k/L       lane = k%L，lane 0 在最低位
scale address   = r*(K/B) + k/B
HiF g0 address  = r*(K/4) + k/4
HiF g1 address  = r*(K/8) + k/8
```

除法均为整数除法。A 的 r 是 token 行，B 的 r 是输出通道行。数据保持 M/N 复用关系，不预先扩展成互不相关的 98,304 对元素。实际 PE scale 物理槽位、未活动 profile 和 valid/握手由后续 testbench 按导出配置映射，不能直接把逻辑 scale 序号当成所有 PE 的物理槽号。

## FP64 golden 和原生 K 视图

`golden/<source>/<format>/dot_full_fp64.mem` 是 64 个输出的理想 K768 dot，顺序 m→n。每行 16 hex 位，表示**未舍入到 FP32 的 IEEE binary64 位模式**。从最终编码独立反量化，乘积用 binary64，累加用 `math.fsum`。golden 和 DUT 均不在此阶段执行 C 反馈。

原生 K 的每个目录另有 `dot_fp64.mem` 和 `k_index.mem`：

- H：K16/32/48/64；Q：K32/64/96/128；E：K32/64/96/128/192/256。
- 每个原生视图仍为每来源 49,152 MAC。每笔为独立 dot+C0，输出顺序 m→n→chunk，chunk 最内层；事务 t 的输出坐标为 `m=(t/chunks)/16`、`n=(t/chunks)%16`、`chunk=t%chunks`。
- `k_index.mem` 每行 16 bit，共 K768 个索引，逻辑 shape `[chunks,native_K]`；每个输出复用同一索引表，不重复存储。testbench 依索引读取 A/B、scale、g0/g1。
- HiF K96 对每三个 K64 block 按 `B0+B1前半`、`B2+B1后半` 组织两笔，A/B 同步映射；其余视图按连续 K 切分。不同分组不要求最终硬件部分和逐位相同。

NV 的上述 golden 全部位于 **PE 局部缩放域**；额外 `dot_source_domain_fp64.mem` 是乘回 global A×B 因子的 K768 诊断值，不能直接拿它比较 PE 输出，也不能把 global 乘到已有 C 的整个 D 上。

后续 ULP 对比保留 FP64 golden，将实际 FP32 结果精确提升到 FP64 后再做差。当前尚未确定 C 反馈、舍入模式验收或 ULP 门槛；文件准备通过不表示 RTL 数值验证通过。

## 检查和追溯

`validate.py` 核对所有 manifest/文件/代码 hash、原始子块坐标、BF16 位模式一致、word 打包、FP6 padding、HiF 微指数、NV global 编码、事务计数与 K 索引。所有 18 组 full-dot golden，以及每个 native K 视图一个输出的全部 chunk，使用独立 `Fraction` 精确有理数结果交叉检查 binary64；所有 partial 文件再核对 FP64 点积。精简结果见 [采集摘要](ai-first-layer-summary.json)。

来源：[Qwen2.5 固定版本](https://huggingface.co/Qwen/Qwen2.5-3B/tree/3aab1f1954e9cc14eb9509a215f9e5ca08227a9b)、[Qwen MoE 固定版本](https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B/tree/1a758c50ecb6350748b9ce0a99d2352fd9fc11c9)、[WikiText](https://huggingface.co/datasets/Salesforce/wikitext)、[OCP MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)、[HiF4 v2](https://arxiv.org/html/2602.11287v2)、[NVFP4](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/nvfp4/nvfp4.html)。checkpoint 自带许可证分别为 Qwen Research License 和 Tongyi Qianwen License；数据集为 CC-BY-SA-3.0/GFDL。工具读取已安装的 Transformers 4.56.0，不把第三方实现复制进仓库。
