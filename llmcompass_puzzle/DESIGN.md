# 系统建模与实施方案

状态：S1 接入验证已实现，S2–S5 为待实施设计；2026-11-13。源码审查基于 [固定版本](../dependencies/llmcompass.json)，路径下的函数名以 [审查记录](source_audit.json) 为准。以下区分上游能力、项目扩展与待校准假设。

## 1. 研究问题与实验对照

主问题不是增加峰值 FP4 吞吐，而是：在总面积、存储容量和可用功率等条件下，**Tensor 配比改变后，哪个系统资源变成瓶颈，协同调整能否产生净推理收益？** 精度迁移为给定情景，不设置 PPL/准确率约束，也不假设真实模型质量已经被验证。

保留三套参考：

| 参考 | 目的 |
|---|---|
| 原始 LLMCompass / A100 | 先复现上游 GEMM、vector 与存储结果，检验接入未破坏框架 |
| A100-derived + 本项目 `1:2:4` | 在相同 DP 合同和系统资源规则下比较九种配比，隔离配比本身的收益 |
| 改配比 + 协同优化系统 | 衡量同时调整 vector、容量和带宽的额外收益及代价 |

实际 A100 没有原生 MXFP8/MXFP4 浮点执行能力。原始 A100 比较采用明确的支持格式执行路径，例如量化存储→解包/转换→BF16 GEMM；不能给 A100 虚构原生 FP4 吞吐。存储格式、乘法格式、累加格式和输出格式分别声明。

每个负载至少比较：固定硬件改迁移方案；固定迁移方案只改 Tensor 配比；固定配比与迁移方案协同调系统参数。预填充和解码分开输出。对未来模型只使用具名情景，不把任意改变精度 MAC 占比写成已经实现的模型。

## 2. 建模架构

```text
N12 DP 综合/功率证据 ── 工艺缩放情景 ── 多精度 Tensor profile
                                           │
A100 基线 ── Tensor 替换 + vector/RF/SRAM/L2/HBM/互连配置
                                           │
DeepSeek 配置/场景/路由 ── 完整算子 DAG ── 精度与量化执行计划
                                           │
        系统容量与面积筛选 → mapper → 分层流量、计算与依赖调度
                                           │
       TTFT / TPOT / 吞吐 / 资源时间线 / 面积 / 功率与能耗范围
                                           │
      固定负载选硬件 ←→ 固定硬件选迁移与映射；Pareto/稳健性
```

实现放在本目录：`profiles/` 管面积/格式与工艺缩放，`adapters/` 连接上游系统、GEMM 和 DeepSeek DAG，`operators/` 管量化及缺少的非 GEMM 算子，`search/` 管参数枚举和筛选，`configs/` 保存输入，`runs/` 保存未跟踪运行结果。按里程碑逐个建立，不先造大框架或复制第三方源码到适配层。

`ratio_dse` 的硬件证据导入、格式打包、GEMM 形状和迁移规则可复用；其固定每 SM refill 带宽的运行时模型不作为新主线的系统访存模型。历史结果只在声明相同边界的子问题中对照。

## 3. A100 基线先统一

上游 `hardware_model/compute_module.py` 内置对象是 108 SM、1.41 GHz、40 MiB L2、5120 B/cycle 全芯片 L2 带宽；每 SM 四个等效 16×16 systolic array、每 cell 每拍一个 MAC、192 KiB 本地 SRAM。`configs/GA100.json` 则配置 128 个物理和运行核心、48 MiB 物理和可用 global buffer。前者用于性能锚点，后者不能原样当作零售 A100 配置。[上游配置](https://github.com/PrincetonUniversity/LLMCompass/blob/2e015fd2ee750e6cad8d7152df52551e5b41ef20/configs/GA100.json)

建议参考 SKU 为 A100 80GB SXM：80GB HBM2e、2.039 TB/s HBM、400W 标称板卡 TDP；108 个启用 SM，完整 GA100 为 128 SM。192 KiB 是组合 L1/shared-memory 总容量，不能全都默认为可分配 shared memory；可用部分单独配置。5120 B/cycle 是 LLMCompass 的模型参数，不是这里新测的 collector 带宽。[NVIDIA 产品规格](https://www.nvidia.com/en-eu/data-center/a100/) · [NVIDIA 架构说明](https://developer.nvidia.com/blog/nvidia-ampere-architecture-in-depth/)

固定记录 `physical_sm_count`、`enabled_sm_count`、`runtime_active_sm_count`；面积按物理单元，性能按启用和调度的单元计。L2、HBM channel 亦区分物理/启用容量与接口数。采用多 GPU 时固定节点设备数、TP/EP、互连拓扑和每方向速率，再与其他候选比较。

原始 A100 复现保留 1.41 GHz。本项目实测 DP 为 N12 1 GHz；缩放并不证明它在 7 nm 下满足 1.41 GHz。主配比实验先在统一 1 GHz 情景进行，并给 A100 归一化同频对照；1.41 GHz 的改造设计只能作为明确的目标频率情景，待时序表征。不同频率场景分别报告，不能混成同条件收益。

## 4. 用真实 DP 面积替换 Tensor 成本

上游 `calc_systolic_array_area_mm2()` 使用按精度估计的 FPU 晶体管数和密度。我们的替换项为完整 DP 实例数乘以工艺代理面积，加尚未包含的阵列外围：

```text
A_DP,7proxy(r) = A_DP,N12_measured(r) / S_A
A_tensor,SM(r) = arrays_per_SM × M_array × N_array × A_DP,7proxy(r)
                 + A_operand_delivery + A_array_control + A_extra_accumulator
A_chip = N_physical_SM × (A_tensor,SM + A_vector + A_RF + A_local_SRAM + A_control)
         + A_L2 + A_NoC + A_HBM_controller/PHY + A_device_links + A_fixed_residual
```

所有面积转换统一到 mm²；DP 输入 µm² 先除 10^6。原完整 DP 中已经包含的 scale、归约、FP32 加法/流水寄存器等不能再次收费；RF/本地累加存储按实际存储边界收费。只替换 systolic 部分，不再次对已经处于 7 nm 的 vector/SRAM/PHY 统一做 DP 缩放。

如果使用原始芯片面积作为预算，先审计上游覆盖范围和残差。残差固定且单列，不能为每个候选反向拟合；如面积分项与实物边界不兼容，使用“同模型总面积预算”对照，不能把模型小计等同完整 die 面积。

**同形状不等于同基线算力。** 上游每 SM 4×16×16×1=1024 MAC/cycle；把每个 cell 直接换成 native-H16 DP 后会变成 16384 MAC/cycle。它是 16 倍计算容量的架构变更，不是仅修改精度配比。必须区分逻辑 MMA tile 与物理 DP 阵列。九配比之间可固定同一物理 M/N；与 A100 比较则显式选择“同面积”或“同 BF16 峰值”锚点。仅就同频峰值而言，64 个 H16 DP/SM 对应 1024 MAC/cycle，但它的几何、调度和时延不自动等价于原始四个 16×16 标量阵列。

## 5. 12 nm→7 nm 的代理缩放与功率

复用仓库已经审查的 [DeepScaleTool 系数](../paper/data/process_normalization/table_inputs.json) 和原表 SHA-256。工具没有直接 12 nm 档，采用 **14 nm 代理 N12**，明确标为 `node_proxy_14_for_12`。既有三位显示系数为面积 `S_A=7.273`、延迟 `S_D=1.132`、能量 `S_E=1.727`，目标值=原值/系数。这是工艺归一化情景，不是 7 nm 综合证据。[工具论文](https://arxiv.org/abs/2102.10195)

固定活动与每次发射的代理能量条件下：

```text
E_issue,7proxy = E_issue,N12proxy / S_E
P_dynamic,7proxy = P_dynamic,N12 × (f_target / f_reference) / S_E
```

同频时动态功率约为原来的 0.579；若另假定频率按延迟系数升至 1.132 倍，则约为 0.655。不能同时再乘一次功率缩放或电压缩放。DP 级 L/II 是周期合同，不因面积缩放就减少流水级数。

N12 动态/漏电分项和活动来源必须保留。上述能量规则不是经验证的漏电迁移规律；7 nm 漏电系数另列未知或具名敏感性参数。输入活动不同导致的动态功率差异也需要区间或后续标定。

上游所审查的硬件/成本/搜索代码没有完整芯片功率模型。新主线需要补充 vector、RF、SRAM、L2、NoC、HBM/controller 和静态底座功率，才能使用整芯片或板卡预算。DP-only 预算仍可以做局部敏感性，但不能把 A100 的400W预算全部分给 DP。总功率采用调度重叠时段的同时活动项之和，能耗按时间积分；缺少分项时输出 `partial_power`，不把缺项当零后宣布满足 TDP。

## 6. Tensor 时延与 SCALE-Sim 的正确接法

保留 LLMCompass 的多级 tile mapper、核心分配、容量检查和重用/双缓冲机制，通过窄接口替换最内层阵列服务估计。原始 A100 保留其 SCALE-Sim/查表后端作复现基线。

本项目多精度阵列的逻辑 M/N/K 固定，native dot 长度随模式与配比改变：`K_steps=ceil(K_logical/native_K)`。`useful_MAC=M×N×K_logical` 不变；issued MAC 另计空间/K 尾部。A/B 存储容量与搬移按原始张量元素、打包和 scale 计算，不能把 K_steps 当作张量 K 后再少算 native_K 倍的字节。

源码中 `simulate_systolic_array_cycle_count()` 对大形状采用0.98/0.99利用率近似，对小形状查表/调用 SCALE-Sim，最终将整个周期数除以 `mac_per_clock`。对于多元素 DP，这会同时缩短原 systolic 的填排项，且不包含本项目 L8/反馈合同；不能只把 `mac_per_cycle` 改成16/32/64就认为接入完成。

拟设统一 `ArrayService` 接口，输入 M/N/K、数据流、native_K、L/II、物理 shape、上下文和容量，输出 issue 数、计算/填排/RAW 周期、各接口请求与峰值占用。两个可区分的实现：

- `native_dp_broadcast`：与现有4×4组内广播、无组内脉动的合同一致，复用已有 DP 级切块和反馈逻辑，但系统访存由 LLMCompass 侧调度。作为已有 DP 阵列假设的主后端。
- `dot_systolic_proxy`：保留 SCALE-Sim 的 systolic 空间调度，K 轮变为向量 dot 事件；每事件的原始字节、scale、链路宽度、hop 延迟和 DP L/II 必须补充。它是额外的数据流情景，经微例校验后才能参与结果，不与广播实现混称同一个阵列。

SCALE-Sim 可继续提供原始基线和明确匹配的数据流利用率；它不会自动证明本项目广播阵列的时延。缓存键必须包括 backend、profile/precision、native_K、L/II、shape、调度、字节布局和资源配置，不能沿用仅 M/N/K 的跨模式查表。

## 7. 分层存储、供数与容量约束

| 层级 | 新主线的计量单位/约束 | 来源与接入 |
|---|---|---|
| HBM↔L2 | 每芯片 byte/s、访问延迟、HBM容量 | 复用 `IOModule`，带宽由 channel×pins×bitrate/8得到 |
| L2/global buffer↔各SM | 每芯片共享 B/cycle、容量 | 复用 `l2_bandwidth_per_cycle` 与 mapper 的跨tile重用，不按每SM复制一份全带宽 |
| SM SRAM/RF↔operand buffer | 每SM端口/银行带宽、容量、复用 | 上游未显式细分，建立参数化校准接口；可先标理想供数上界，不能冒充已建真实collector |
| operand buffer↔DP | 每阵列发射向量宽度、缓冲bank、L/II | 由选定 ArrayService backend 与数据流合同负责 |
| GPU↔GPU | 每方向带宽、消息延迟、拓扑 | 上游 all-reduce 可复用；MoE all-to-all 需要新算子与通信图 |

同一层的搬移只计一次；上游 SCALE-Sim 使用 `InterfaceBandwidth: CALC`，原本主要提供阵列周期，不能再把其生成的内存行为与上层流量重复收费。已有上层代码对 tile 重用、双缓冲和末尾排空有明确逻辑，改精度字节账本时保留这些依赖。

HBM 容量检查包含**全部需驻留权重**、KV/cache、scale、激活、临时工作区及转换展开缓存；MoE 的激活专家参数量不能替代全部权重驻留量。放不下时明确多设备分片或显式 offload，不静默忽略。L1/L2 中的 A/B、FP32 C/D、scale 与 ping-pong 副本按真实生命周期计算，不用单一 `word_size` 统一覆盖。

HBM 扩带宽须匹配合法 channel/pin-rate/capacity/PHY/cost 组合；L2 带宽与 bank、端口和互连关联。上游搜索直接令 L2 带宽随容量线性变化，可保留为命名对照情景，但新主线不能把该耦合当作通用物理定律。SM 局部带宽未表征前，给上下界/敏感性结果，系统框架的存在不消除这个未知量。

## 8. Vector 与量化开销

上游提供 vector unit、Softmax、LayerNorm、GELU 等，并已在 split-K 部分和合并中使用 vector 吞吐。DeepSeek 还需要 RMSNorm、SiLU/门控、RoPE、路由/top-k、稀疏 gather/scatter、压缩/KV更新等相应算子或可验证分解。

修改 vector 算力必须同步修改成本。上游吞吐由 `vector_width × sublane_count × flop_per_cycle` 构成，而面积分别读取 `int32_count/fp16_count/fp32_count/fp64_count`。仅增加吞吐字段会造成免费加速。首轮保持warp宽度与 Tensor 数量独立，以合法 vector 资源 bundle 同步配置浮点、整数、特殊函数/归约吞吐、RF/端口和面积；若增加 sublane 同时增加 Tensor 单元，需要明确记为另一组结构变化。

量化定义为显式算子/融合recipe：

```text
producer → block reduction(absmax等) → scale计算 → round/clamp/convert
         → pack及scale写入 → low-precision GEMM → 可选反量化/输出转换
```

- 离线权重校准/量化是部署成本，单列，不逐token重复。
- 在线激活量化、scale归约/生成、位打包主要占用 vector、整数、归约/SFU 和访存资源；不应只按等价 FP FLOP数除vector峰值。
- W4存储→MXFP8执行的展开占据转换单元和临时容量；HBM字节按W4存储，阵列侧按展开后格式，不能在两侧都按W4或都按FP8计。
- K分块累加、Softmax、RMSNorm等与量化共享 vector；它们的时间和资源竞争不能分别忽略。
- 若量化融合到producer/consumer，可减少launch和中间写回，但仍消耗指令、端口与寄存器。融合与非融合分别建recipe，按依赖和资源确定重叠，不无条件取各项最大值。

由此可检验“FP4阵列更快却因量化/Softmax/路由而没有端到端收益”，以及补充 vector 资源是否比继续增加 FP4 容量更有效。若存在专用量化单元，另设硬件情景并计算其成本。

## 9. DeepSeek DAG 与未来情景

保留已有 V4/V4.1 adapter、config hash、MoE token分布、SWA/CSA/HCA、候选索引与四种累计迁移规则，但从 GEMM 账本扩展成带 tensor 生存期和非 GEMM 节点的 DAG。不得把上游标准 dense Transformer 直接改一个模型名字就作为 DeepSeek。

每条算子记录输入/输出shape、存储/计算/累加精度、依赖、权重身份、路由/索引、KV所有者、融合recipe、执行设备。按层×分段×算子进行复用缓存，但保留串行依赖、专家不均衡和跨设备通信。

保留 `query_tokens`、`past_tokens`、batch、decode步数、prefill/简化CED/full日程。首批工作负载组为实际配置的两个模型×四迁移方案×短/长上下文×prefill/decode；未来组再独立变化激活专家数/路由不均衡、上下文/压缩、精度执行分布。每种变化生成具体DAG并守恒其声明的数学工作，不把未来情景当作模型能力预测。

多设备首先固定一种完整可执行TP/EP配置，报告每设备权重与KV容量、all-reduce/all-to-all。未实现某种通信则标 `unsupported_parallelism`。可先做单层和单设备局部校验，但不能把局部结果叫完整模型TTFT/TPOT。

## 10. 搜索方式与预算

沿用上游“离散枚举→面积/容量筛选→roofline筛选→详细mapper”的结构，新增配比、精度和量化路径。源码现有搜索枚举device/SM/sublane/array/vector/SRAM/L2/memory参数，以延迟目标下总面积最小为目标；我们的主目标改为固定资源预算下的 TTFT/TPOT Pareto，并保留成本目标作为独立视角。

分阶段控制搜索维度：

1. **配比主效应**：9个配比×4迁移；固定shape、SM、vector、存储与频率；超面积者标不可行，不擅自扩芯片。
2. **Tensor/vector平衡**：在每个配比下搜索合法vector资源bundle，并按同面积预算重新求可安装SM/DP。报告安装、启用、运行时活跃三种数量。
3. **系统协同**：加入HBM bundle、L2容量/bank、SM SRAM/RF与局部供数情景；先二维/三维敏感性，再在非支配附近细化联合网格。不是只对单轴最优点做贪心拼接。
4. **量化与未来负载**：对每个硬件重复融合/非融合量化和上下文/专家分布情景，比较固定硬件迁移收益与重新选硬件后的收益。

筛选顺序为格式/物理合法性、HBM/KV/局部容量、面积、已具备证据的功率范围、保守时延下界、详细调度。只有真正乐观的下界才能硬剪枝；经验预测仅作排序，避免丢失解。大空间缓存重复形状，固定seed/参数网格，记录所有淘汰原因，保存多个Pareto候选而非单一分数。

默认不自定义“精度质量代价”。优化函数包括TTFT、TPOT、tokens/s、面积和可用范围内的功率/能耗；不把未校准功耗混成精确成本。输出对工艺代理、局部供数、量化成本、活动率和路由分布的敏感性及最坏后悔值，检验最佳配比是否稳健。

## 11. 输入输出合同

| 输入文件 | 粒度与必要参数 |
|---|---|
| `dp_profiles` + `process_scenario` | 九DP、原始area/dynamic/leakage、模式native_K/L/II、格式与证据hash；工艺代理、频率及未知项 |
| `system_baseline` | 物理/启用SM、Tensor组织、vector bundle、RF、SM SRAM、L2、HBM、设备拓扑与频率 |
| `workload` | 模型config/revision，prefill/decode、query/past/batch、路由、TP/EP与存储策略 |
| `precision_plan` + `quantization_recipe` | 逐算子格式、四累计方案，在线/离线转换、融合/展开、资源与字节规则 |
| `search_space` + `constraints` | 合法资源bundle/枚举范围、面积/容量/可用功率约束、延迟目标和稳健性场景 |

输出至少包含 `candidate_specs`、`area_breakdown`、`operator_timeline`、`traffic_by_level`、`memory_lifetimes`、`power_breakdown`、`infeasible_candidates`、两方向selection、Pareto与manifest。每项区分原始实测、工艺代理、上游解析、项目扩展和未知；输出时间以秒、带宽以byte/s或注明B/cycle、面积mm²，MAC按2 FLOP换算。

TTFT包括明确范围内的prefill与首token路径，TPOT给定历史KV下的decode关键路径；不包含排队/服务调度时需写明。HBM不足、未知非GEMM/通信或必需功率项缺失时，不输出“完整可行且准确”的标签。

## 12. 实施顺序与验收

| 阶段 | 可审查交付 | 通过条件 |
|---|---|---|
| S0（已完成） | 固定源码、审查、基线差异、缩放/接口与搜索方案 | 不改旧DSE；来源和待建模边界明确 |
| S1（已完成） | 锁定运行依赖、A100规范化配置、GEMM/Softmax重放；DP面积/工艺代理和vector成本接入 | CPU案例可复算；面积替换守恒；物理/启用资源独立；不虚构N7时序/泄漏 |
| S2 | 逐精度ArrayService与混合字节布局 | 模式峰值、K尾部、L/II、FP32部分和、scale字节、面积不重计；scalar模式与上游交叉验证 |
| S3 | DeepSeek DAG、非GEMM与量化recipe、必要通信 | 逐算子形状/依赖/生存期守恒；容量和通信完整；独立量化微例与时间线校验 |
| S4 | 两方向系统DSE、主要消融、稳健性与图表 | 固定预算/同负载比较；所有瓶颈、加速和代价可追溯；不预设FP4一定更快 |
| S5 | 硬件校准/持出测试与更广参数空间 | A100参考kernel或可信trace校准；新DP阵列与功率按能获得的证据单列准确度 |

优先图形：Tensor配比×vector配置的延时热图（按HBM/精度方案分面）；同一迁移方案下tensor/vector/quantization/访存/通信的关键路径分解；TTFT–TPOT/成本Pareto与不确定性带。结果未运行前只定义待检验假设，不提前写出创新结论。
