# 配比驱动的系统资源重分配：MoE 阶段

研究主线：**在相同面积与功率预算下，改变 Tensor 精度配比后，重新分配 SM、vector 和存储资源，是否仍能优于同样优化过的原配比系统？** 精度迁移改变需求，系统参数调整改变供给。主线不以最高 FP4 峰值或最大搜索规模为目标。

本阶段是可执行的 DeepSeek-derived **单个典型 MoE prefill 子层**，用于隔离专家迁移机制。面积调用固定版 LLMCompass 成本模型；时序是新增的解析适配器，并非上游 SCALE-Sim 对新 DP 的验证结果。不能将结果乘层数后称为完整 TTFT。

## 预先确定的对照

[moe_system_study.json](configs/moe_system_study.json) 的 `study_design` 明确主问题和固定资源对照。主案例为 V4-Flash、全 EP 组 2048 token、融合量化。256 token 和 V4.1 用于检查负载依赖；融合开/关为配对消融。每个功率预算独立比较。

1. **只改配比**：固定 128 个物理 SM、108 个启用 SM、vector 1×、80 GB/2.039 TB/s HBM、40 MiB/5.12 TB/s L2，只换九种配比。超预算点标为不可行，不能作为推荐。
2. **系统协同**：对每个配比搜索同一个资源池。比较各配比的最优方案，特别是与经过相同优化的 `1:2:4` 比较。报告 SM、vector、HBM、L2 的具体选择，不能把通用资源调整收益全部归因于配比。
3. **模型迁移**：固定每个完整硬件设计，比较 W4A8、MXFP4 W4A4、NVFP4 W4A4；反向固定迁移方案选择硬件。质量门禁独立于成本排名。

只有上述对照显示瓶颈或排名变化后，才有理由细化对应资源区间。本批不增加新的搜索维度。所有最优均为**给定离散池内最优**。

## 输入与运行

```bash
python3.11 llmcompass_puzzle/setup.py --check
bash llmcompass_puzzle/run_system_dse.sh llmcompass_puzzle/runs/my-moe
# 自定义配置作为第二个参数；输出目录必须是新目录
bash llmcompass_puzzle/run_system_dse.sh llmcompass_puzzle/runs/my-case my-config.json
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.summarize_system \
  --run llmcompass_puzzle/runs/my-moe --output llmcompass_puzzle/runs/my-moe-summary
```

| 输入 | 参数、单位和约束 |
|---|---|
| `models` | 已冻结的模型 config 名称；读取 dim、MoE 宽度、全部专家数、top-k、层数；revision 来自 `paper/data/evidence/model_sources.json` |
| `tokens` | 整个 EP 组本次 prefill token 数，不是每卡 token；必须能被设备数整除；没有 past-context 轴 |
| `plans` | `w4a8`、`routed_mxfp4`、`routed_nvfp4`；只改变路由专家，shared 保持 MXFP8 |
| `physical_sms` | 安装数量；启用数按 `floor(N×108/128)`；每 SM 四个 4×4 DP 阵列、1 GHz、L8/II1 |
| `vector_scales` | 0.5/1/2；同步上游 ALU/RF 端口面积；有效 FP32-equivalent 服务率为 `128×scale×f` work/s/SM |
| `hbm_bundles` | 物理/启用 channel、十进制 GB；带宽按 active channels×407.8 GB/s；PHY/controller 面积随资源变化 |
| `l2_bundles` | 物理/可用 MiB、bytes/cycle；容量和带宽成套配置，全芯片共享 |
| `settings` | 8 卡 EP；144 KiB 可用 SM SRAM；tile 候选、启动时间、互连、量化工作系数、其他状态 HBM 预留 |
| `caps_w` | 含 HBM 的设备功率情景，W；null 不设功率限额。不是已校准的实际 TDP |
| `power` | 明确的静态/空闲 W、J/work、J/byte、DP 活动修正；本批均为标记过的情景假设或 DP 代理 |
| `numerical_recipes` | quantizer revision、校准数据 SHA、完整数值图 SHA；未绑定时质量必为 unknown |
| `quality_policy` / `quality_records` | 质量阈值及独立评测记录；参见 [质量接口](QUANTIZATION_AND_QUALITY.md) |

九 DP 的面积、native K、L/II 和 BF16/MXFP8/MXFP4 动态功率来自已有实测证据，经既定 N12→N7 工艺代理转换。NVFP4 用自己的 native K/存储布局，但其动态功率暂无测量；`power.dp_mode_proxies` **显式**采用 MXFP4 代理。该选择不是两格式实测功率相等的结论。

## 内部结构与粒度

`system_search.py` → `make_design()`：调用 LLMCompass 的 vector、RF、SRAM、L2、I/O 成本，移除原标量阵列面积，加入实测 DP 面积。面积上限来自归一化上游基线，约 826.764 mm²；不是实物 A100 die 面积。HBM 堆栈封装成本不在 silicon-area 目标中。

`evaluate()`：依次执行 Norm、FP32-equivalent router、共享输入量化、EP dispatch、专家 gate/up、SwiGLU、down 量化/down、shared expert、EP combine、残差。采用顺序 kernel 与阶段 barrier，不假设 shared/routed 分支并行。router 为归约/选择等合并的粗粒度服务模型；不覆盖哈希路由层、mHC、Engram、attention、视觉或 MTP。

**驻留容量** = 所有 MoE 层的所有 routed expert 权重/EP + replicated shared expert 权重 + 8 GiB 显式其他状态预留 + 子图活跃数据估计。不是 top-k 权重；8 GiB 不构成整个模型、特别是 V4.1 Engram 的驻留保证。此处无 offload、KV 或完整图生命周期分析。

**GEMM 映射**保留 M/N 向物理 4×4 DP 网格取整、K 向 native K 取整、启动/流水延迟。tile 需要双份 A/B、FP32 累加器；W4A8 另需 packed W4 buffer 和本地展开工作。超过 SRAM 或保守 L2 panel 约束的映射不可行。当前每个 kernel 以同类 tile 均匀服务近似，未模拟 bank 冲突、RF 端口冲突及 collector 仲裁。

**分层数据流**：

- 每个 GEMM 的冷权重从 HBM 读取一次；无跨算子/请求权重缓存。B 的 N-panel 驻留 L2 后复用，L2→SM 流量按 M tile 重用情况计算。
- A 的 L2→SM 读取按 N tile 计算；若工作集溢出 L2，则 HBM 的 A 读取也按 N-panel 重复计费，不能同时假设 B 驻留和免费保留全部 A。
- 输出为 BF16，scale/尾部计入 packed 字节。工作集是否溢出 L2 使用显式粗粒度估计，不是精确缓存模拟。
- 双缓冲 pipeline 使用 `Σstage_time/batches + (batches−1)×max(stage_time/batches)`，保留填充和排空；计算可等待供数。不是要求每周期换新 A/B。
- HBM、L2、link 各自有共享速率；本批没有独立 collector 带宽模型。片上 SRAM/RF 服务假设足以维持所建 DP/vector 服务，后续需校准或添加瓶颈限制。
- EP 使用指定的 all-to-all 解析路径，包含 send/receive 的 L2 流量；路由均衡是主实验假设，`routing(...,'hot')` 用于不均衡检查。逐阶段取最慢 rank，不以平均 token 隐藏热点。这里的通信路径不是原始 Python 的 replicated-input 部署。

**量化**：block-local amax/scale、转换、pack 通过 vector/special 等效工作计费。NVFP4 假设离线校准的固定 per-tensor scale，在线更新 group16 scale。W4A8 是优化后的 MX32 研究对照，不逐字复现 V4 的 activation group128 实现。每种输入表示只量化一次；A4 routed 与 A8 shared 需要两种表示。融合取消量化独立 launch 和 producer 重读，但仍保留量化运算、低精度输出及保守的高精度中间结果写回。

**功率**：逐 kernel 枚举 1、1/2、1/4 活跃 SM 和 1、1/2 供数速率，重新计算延迟。准入采用该 kernel 可能同时活跃的资源峰值包络之和，偏保守；不以整次平均功率放行，也不按 `P/Pcap` 事后缩放时间。安装资源的 base 不因少开核心而消失。DP 代理之外的 vector、局部存储/RF、L2/NoC、HBM、link 成本为包含相应路径的等效系数，未逐组件校准。`energy_j_proxy_upper_per_rank` 是最忙 rank 的分阶段能量上界代理，不是八卡总能量，也不是实测能量。

## 输出与解释

| 文件 | 含义 |
|---|---|
| `designs.csv` | 配比、安装/启用 SM、vector、存储容量/速率、面积与预算可行性 |
| `candidates.csv` | 每个工作负载/方案/硬件的秒数、功率包络、能量代理、容量、状态及稳定 ID |
| `operator_breakdown.csv` | 每阶段实际模型时长，以及可重叠的 matrix/vector/HBM/L2/link 服务时间；服务时间不能直接相加当阶段时长 |
| `cost_only_selections.csv` | 两个方向的成本最优；不代表质量达标 |
| `quality_constrained_selections.csv` | 所有质量要求均有匹配证据且通过后的两个方向最优；当前为空 |
| `paired_comparisons.csv` | 最佳候选与同场景优化后的 `1:2:4`；gain 为 `T_baseline/T_best−1`，不是延迟下降比例 |
| `quality_bindings.json` | 模型/完整数值方案的质量键和状态 |
| `config.json` / `manifest.json` | 原始配置、输入/代码/输出 hash、范围和校准状态 |
| summary 的 `controlled_cells.csv` | 固定资源与逐配比优化资源两类配对单元；primary 子集与量化融合消融另存 |

淘汰状态区分面积、驻留容量和功率/映射不可行；后者合并表示当前离散策略找不到可执行点，不证明任意其他映射也不可行。`largest_stage` 仅表示最长单阶段，不能代替全图归因。

## 验证与后续准入

本批测试检查全部专家驻留、路由 MAC 守恒、热点不平均化、量化 metadata/融合工作守恒、本地展开不写回 HBM、溢出重读、容量淘汰、每阶段功率限制、质量未知不放行以及 CLI/manifest。它们是软件合同检查，不是新芯片时延准确性验证。

硬件校准应按层进行：①单 DP 的功率活动和 N7 时序/泄漏；②实际 grouped GEMM 的 M/N/K、尾块和本地转换；③独立与融合 block quant/Norm 的时间及增量功耗；④L2/HBM 不同工作集、通信和重叠；⑤未参与拟合的组合 MoE trace。实际 A100 只能验证它支持的路径，不能给改造 FP4 DP 提供实测背书。

保留至少一组未用于选择参数的 token/路由/shape 作为验证；质量独立用完整模型协议验证。若增加旋转、SVDQuant 等算法，先补对应算子/存储，再接其质量成绩。完整 prefill 的结论必须在 attention、mHC、Engram 等图补齐后重新比较。
