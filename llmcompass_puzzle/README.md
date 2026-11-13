# LLMCompass-Puzzle：多精度配比与系统参数协同设计

本目录是与 `ratio_dse/` **并行、独立**的研究主线，保留原模型和实验。以 prefill 为主、decode 为对照，研究在面积、存储和可用功率预算下，如何共同选择 Tensor 精度配比、vector、存储/带宽及模型精度迁移方案。

**当前已完成 S1 接入验证**：真实调用固定版本 LLMCompass 成本模型，接入九种实测 DP 的工艺代理/面积替换；运行原始 A100 的 SCALE-Sim、GEMM mapper 与 Softmax CPU 仿真。尚未接入多精度 DP 时序及 DeepSeek 完整算子图，**本阶段没有端到端推理加速结论**。

## 运行

从项目根目录执行；Python 3.11+，CPU 即可，不需要 CUDA、GPU 或 PyTorch。首次安装需要访问公共 Git/Python 包仓库。

```bash
python3.11 llmcompass_puzzle/setup.py
python3.11 llmcompass_puzzle/setup.py --check
bash llmcompass_puzzle/run_reference.sh llmcompass_puzzle/runs/my-reference
llmcompass_puzzle/.venv/bin/python -m unittest discover -s llmcompass_puzzle/tests -v
```

输出目录必须不存在，旧结果不覆盖。仅重算面积/峰值或使用自定义 S1 配置：

```bash
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.characterize \
  --config llmcompass_puzzle/configs/characterize.json \
  --output llmcompass_puzzle/runs/my-area
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.replay \
  --output llmcompass_puzzle/runs/my-a100
```

SCALE-Sim 在部分 Python 警告配置下会报告上游 topology 文件句柄的 ResourceWarning；测试必须仍检查退出状态和数值。本地环境、第三方源码和大运行产物被忽略，仅提交适配代码、配置、版本和精简证据。

## 当前可执行输入

[characterize.json](configs/characterize.json) 是 S1 可执行配置。[study_plan.json](configs/study_plan.json) 是后续 DSE 的声明式研究计划，不能作为推理仿真配置使用。

| 字段 | 单位、含义和限制 |
|---|---|
| `dp_evidence` | 项目根目录相对路径，锁定的九配比 N12 综合/功耗证据 |
| `common_clock_hz` | 正整数 Hz；默认同频 1 GHz，非 N7 时序保证 |
| `physical_dp_shape` | 每个 Tensor 阵列的物理 DP 行列；默认 4×4，区别于逻辑 MMA shape |
| `arrays_per_sm` | S1 固定为 4，改变 sublane 组织留待独立结构实验 |
| `vector_scales` | 从 0.5、1、2 选择；联动 ALU 数、吞吐和 RF 端口成本，固定 warp 宽度 |
| `extra_tensor_mm2_per_sm` | 每个物理 SM 的新增阵列外围面积，默认 0 是显式假设，支持敏感性输入 |
| `process` | N12 用 14nm 代理映射到 7nm；面积/延迟/动态能量除数，泄漏未知 |

S1 系统基线固定在 `backend.baseline_config()`：128 个物理 SM、108 个启用 SM、4 阵列/SM、192 KiB 本地 SRAM、48 MiB 物理/40 MiB 启用 L2，沿用上游 I/O 成本参数。HBM 有效 pin rate 归一到 2.039 TB/s；上游模板容量字段虽叫 `GB`，转换器按 GiB 读取，因此设置为 `80e9/1024³`，与内置参考的 80e9 byte 一致。它不是通用硬件搜索配置。面积按物理单元，峰值按启用单元。默认 4×4 DP 的 BF16 K16 吞吐与原始四个 16×16 标量阵列同频等峰值；4×16×16 DP 则是额外 16 倍 BF16 吞吐的不同硬件情景。

工艺代理 `area/7.273`、`dynamic_power/1.727 × target_frequency/source_frequency`；不把动态缩放套到泄漏，不额外重复乘电压因子，不据 delay 除数宣称目标频率已通过。保留全部 N12 原始证据和未知项。DP 测量活动率来自原有回放，非 DeepSeek 的直接功率测量。

## 当前输出

| 文件 | 内容及边界 |
|---|---|
| `area/normalized_a100.json` | 同频 A100-derived 配置，物理/启用资源分离 |
| `area/a100_area_breakdown.json` | 上游 compute/IO 与单 SM 组件面积，mm² |
| `area/dp_profiles_7nm_proxy.json` | 原始证据及逐格式 native K、L/II、面积与动态功率代理；未知泄漏/目标时序为 null |
| `area/tensor_vector_area_candidates.csv` | 九配比×三 vector 档的面积、预算可行性、逐格式 TFLOP/s 与 DP 动态功率代理 |
| `reference/a100_replay.csv` | 三个标量阵列周期案例，其中两个含原始 A100 GEMM 映射/秒数 |
| `reference/a100_vector_replay.csv` | 两个原始 A100 Softmax CPU 仿真案例及映射/秒数 |
| 两处 `manifest.json` | 固定依赖、输入/源码/输出 SHA-256、运行范围、单位与假设 |

参考 CPU 重放保留上游 1.41 GHz；DP 面积/峰值表默认 1 GHz。二者是分开的接入验证，不能相除得“加速比”。重放不包含 GPU 测量和完整 launch/模型/通信时间。HBM、L2 与局部供数须分层；不再用旧每 SM refill 带宽代替系统存储模型。S1 也不声称提供 collector 端口仿真。

## 实验与后续接口

- [四个问题与成对实验](EXPERIMENTS.md)：只改配比→瓶颈→协同最优→精度迁移；同预算优化基线；融合 Norm 的量化增量。
- [系统设计及 S2–S5 验收](DESIGN.md)：多精度 ArrayService、混合精度字节、算子图、通信、分层调度、两方向选择与功率边界。
- [S1 运行记录](records/s1-20261113/README.md)：本阶段实际结果、测试和局限。
- [依赖锁](../dependencies/llmcompass.json)、[源码审查](source_audit.json)、[硬件证据](../ratio_dse/configs/area/dp_n12_20261112.lock.json)、[现有负载解析](../ratio_dse/compute_model/README.md)。

LLMCompass 固定到 `2e015fd2ee750e6cad8d7152df52551e5b41ef20`（BSD-3-Clause），`ttm-cas` 子模块固定到锁定 revision。源码放在 `upstream/LLMCompass/`，稀疏检出并初始化成本子模块，不下载庞大历史查表，重放自行生成小型查表。没有修改上游源码；适配器仅在内存中把 matmul/softmax 的 eager Torch 导入变为可选，CPU 时序算法保持原样。GPU helper 不属于当前接口。
