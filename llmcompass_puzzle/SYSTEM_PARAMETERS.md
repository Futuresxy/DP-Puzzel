# 系统参数、量化开销与功率约束

2026-11-13；基于固定版 LLMCompass 与 S1 面积接入。研究对象是 **给定预算下的模型推理系统**：DP 配比是输入，不继续把微架构作为主要搜索对象。本文定义后续联合 DSE 的参数与约束，并记录已实现的量化工作量/窗口功率准入接口。它们尚未与 DeepSeek 完整时序图连接，不构成已跑通的端到端 DSE。

## 1. 主搜索变量与固定边界

| 类别 | 应保留的变量 | 与其他部分的联系 | 首版处理 |
|---|---|---|---|
| Matrix | 九种 DP 配比；全芯片 DP/SM 数 | 精度峰值、面积、逐模式动态能量、可同时启用数 | 物理阵列 shape、L8/II1 固定；配比为主轴 |
| 核心配置 | 物理 SM、启用 SM、每阶段活跃 SM | 面积按物理数量；静态功率按安装资源；性能按调度活跃数量 | 面积先给安装上限，再试若干安装数；功率决定运行并发，不默认装满/开满必优 |
| Vector | 每 SM 吞吐档、整数/转换与归约/SFU 有效服务率 | Norm、Softmax、路由、量化、部分和归约竞争资源；ALU/RF 成本联动 | warp宽度保持32；0.5/1/2×资源档，特殊函数/转换系数独立表征 |
| HBM | 有效带宽、容量、物理/启用 channel、HBM/PHY成本和功率 | 权重、KV、临时张量；面积、静态功耗和每字节能量 | 使用具名合法资源组合，不能独立免费放大带宽 |
| L2/global buffer | 物理/可用容量、全芯片共享带宽 | 缓存/分块重用、FP8展开工作区、供给各SM、跨阶段流量 | 容量与带宽分别记录；上游线性联动只作为一个资源组合假设 |
| SM SRAM/RF | 可分配 SRAM、寄存器/端口、buffer 副本 | tile大小、并发上下文、融合占用、ping-pong可行性 | 主搜索先固定；做容量敏感性，再在瓶颈处细化，不能把192KiB组合L1全视为可分配sharedmem |
| 功率 | die或含HBM设备边界、功率上限、活动窗口、分项能量区间 | 同时限制matrix/vector/访存并发；可能改变最佳核心数和配比 | 固定频率下限制并发；暂不搜索没有电压/时序证据的DVFS |
| 负载 | prefill chunk、query/past、batch、路由分布、四迁移方案 | GEMM大小、专家token数、KV/权重容量、量化摊销 | 模型配置固定；上下文/batch作为场景轴，不与硬件变量混成一个分数 |
| 多设备 | 设备数、TP/EP、互连带宽/延迟 | 全部专家权重驻留、all-to-all/all-reduce、最慢rank | 首轮固定部署；容量不够就判不可行或显式换部署，不能静默offload |

推荐主循环为 `ratio × vector_bundle × HBM_bundle × L2_bundle × physical_SM_choice`，每个硬件再评估四迁移、上下文/batch和功率上限。先过滤容量、面积与格式，再映射与功率校验；在排名改变的区域细化。SM SRAM、量化系数、局部带宽先作为少量敏感性对照，避免所有轴一次性做大网格。

量化方案会改变使用的硬件资源，因此模型侧不能只提供“各精度FLOP占比”；应提供算子shape、共享tensor身份、存储/乘法/累加/输出格式和合法融合边。首版接受模型config+runtime+迁移计划，或显式算子trace；无需读取全部checkpoint权重，也不自动从任意Python推断融合。

## 2. 当前上游可复用什么、还缺什么

固定源码位置见 [source_audit.json](source_audit.json) 和 [依赖锁](../dependencies/llmcompass.json)。

- `hardware_model/compute_module.py`：vector、matrix、SM、频率、SRAM、L2。Vector仅有等价FLOP与exp系数，不是完整INT/convert/SFU吞吐模型。
- `software_model/matmul.py`：HBM/L2流量、tile容量、重用、双缓冲与映射。其 `M==1 or N==1` 的 heuristic 路径使用vector吞吐；这可能影响小batch专家GEMM，需标明实现路径，不能把所有工作一律除Tensor峰值。
- `software_model/softmax.py` 等：非GEMM时序入口。逐算子重叠假设不同，不能用一个全模型 `max(matrix,vector,memory)` 代替依赖调度。
- `design_space_exploration/dse.py`：离散硬件搜索、面积/roofline/详细映射筛选；L2带宽随容量线性变化是搜索假设。仅改变 `core_count` 不保证同步 `physical_core_count`，我们的适配层必须处理两者。
- `cost_model/cost_model.py`：SM内vector/RF/SRAM、L2、controller/PHY及互连面积。单独改vector吞吐不会自动增加ALU计数/端口成本；S1已经做了耦合。
- 上述模块没有整芯片功率准入、DeepSeek完整图或动态量化recipe。上游FP16字节模型也不能直接表示FP4 payload+scale、W4存储/FP8执行和FP32累加。

系统时序粒度采用**顺序kernel图+tile内重叠**。各kernel保留Matrix/Vector/访存/转换服务与依赖，允许真实合法融合；先不引入通用乱序执行或逐周期NoC。局部collector带宽采用独立参数/上下界，不伪装成已校准端口。

## 3. 量化：完整路径都计费，迁移比较增量

必须为 baseline 和每个迁移方案构造完整执行路径，再比较二者总时延。FP8 baseline 不是免费输入：它也可能需要激活amax/scale、转换与权重展开。FP8→FP4不能在基线开销上简单再叠加一套完整FP4量化，否则会重复计费。

现有 `build_gemm_plan()` 对路由专家baseline声明 **W4存储、FP8执行**，并且旧模型边界在展开之后。迁到W4A4时：

- 已经是W4的权重HBM容量/字节不会再次减半；共享专家等原先FP8存储的权重需要单独判断。
- 可以省掉原W4→FP8展开及其工作区/写回，增加或替换对应的激活转换。
- 激活格式、元数据、tensor生存期以及L2/SM供数仍可能改变。
- 能否缓存展开权重决定它是每次使用收费还是跨请求摊销，缓存占用必须同时扣容量。

首版仅支持具名的block-local MX recipe，保留三个计数系数：每元素vector工作、每block特殊/归约工作、每32bit打包字的vector工作。它们是可校准的工作单位，不等价于保证存在的ISA指令数。不建完整量化算法搜索，不计离线训练/校准成本，不计PPL。若未来recipe要求rotation、迭代处理或全tensor扫描，必须另加路径，不能沿用这三个系数声称已经覆盖。

对形状 `rows × K`，block大小G：

```text
N_values = rows × K
N_blocks = rows × ceil(K/G)                 # 不跨行共享scale
Q_vector = c_element × N_values + c_pack × N_packed_words
Q_special = c_block × N_blocks
```

vector与special若共享issue资源，首版以串行服务和计算；只有有独立端口/资源证据时才建重叠。不能把整个量化工作全部除以FP16 FLOP/s。内存字节按目标格式实际打包、scale和尾部计算，事务对齐由mapper负责。Norm、Softmax与量化的vector工作汇入同一资源账本，不各自占用一份完整vector能力。

**Norm融合的可见收益是省launch与中间访存，量化运算仍执行。** 当对应producer合法且高精度结果不再被其他consumer使用时，可替换高精度输出写回，并取消量化kernel对它的读取；低精度输出及scale默认仍物化。若其他consumer还要高精度结果，则不能删除该写回。MoE共享输入只量化一次；路由后专家中间激活按各自tensor计。Softmax→PV不是Norm融合，需要另行标记合法epilogue。

MXFP8的32元素局部block规则见 [Transformer Engine MXFP8](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/mxfp8/mxfp8.html)。全tensor current scaling的两遍读与局部block保留不是同一路径，不应强行给所有量化加两次HBM读取，见 [Current scaling](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/fp8_current_scaling/fp8_current_scaling.html)。融合可降低处理开销，但不证明本项目任何候选的具体加速值，见 [Performance considerations](https://docs.nvidia.com/deeplearning/transformer-engine/features/low_precision_training/performance_considerations/performance_considerations.html)。这些资料用于机制依据，不将训练反向传播所需的双转置/双量化照搬到推理。

消融保留理想零转换增量上界、合法融合、独立转换三个方案。报告完整 `T_new−T_base`；同时从时间线上计算暴露的转换增量，而不是直接把量化kernel服务总和当作端到端惩罚。

## 4. 面积、容量、带宽和功率共同限制候选

```text
A_physical(design) <= A_budget
weights_all_resident + KV + scales + live_activations + workspace <= HBM_capacity
tile_operands + FP32_accumulators + scales + buffer_copies <= allocated_SRAM/RF
同一时段各SM/引擎的HBM、L2请求总和 <= 对应层级共享带宽
每个活动窗口的系统功率上界 <= 同边界的功率预算
```

MoE全部驻留权重不能用top-k激活参数量代替。双缓冲副本不是免费容量。带宽限制是各层资源的竞争和排队，不是要求每周期A/B都换新，也不是把所有层级吞吐直接相加。带宽不足可以stall，stall改变时间和活动功率，需回到调度中反映。

对活动窗口w，采用少量分项动态能量系数：

```text
P_w = P_base(installed_resources, clock)
      + [Σmode issues_mode × e_DP,mode
         + work_vector × e_vector + work_special × e_special
         + bytes_RF/SRAM × e_RF/SRAM + bytes_L2/NoC × e_L2/NoC
         + bytes_HBM_path × e_HBM_path + bytes_link × e_link
         + other_dynamic_energy] / duration_w
E_request = Σw P_w × duration_w
```

同一窗口中的matrix、vector、搬移功率相加；它们在不同窗口各自达到峰值时，不应把所有峰值直接相加而误判。反过来，整次请求平均功率低于上限不能掩盖某个重叠窗口超限。窗口是近似恒定活动的kernel/tile阶段，首版不模拟电源瞬态、热RC或droop。

`base` 包括当前物理设计全部静态/空闲功率，关闭调度不自动省去泄漏；数据搬移系数是相对于base的增量，HBM路径含HBM、控制器、PHY，避免漏计和重复计。若约束是die功率，排除外部HBM并使用同边界的cap；如果是含HBM设备功率，必须包含它，不能混用板卡TDP与die subtotal。

DP能量可从已有固定频率活动代理 `P_dynamic/f` 起步，但这不是通用工作负载实测能量；vector、RF、SRAM、L2、HBM和静态功率仍需证据或明确区间。每个系数使用 `[lower, upper]`，来源、工艺、频率和组件边界随设计绑定。未知项填null，不凑残差让某个配比刚好过关。

准入分四种：上界也满足→`robust_feasible`；下界已超限→`infeasible`；上下界跨越限制→`uncertain`；存在必要未知项→`unknown`。只有第一种进入严格可行集合，且它表示**在声明系数区间和窗口模型内**可行，并非完成实物功率验证。

固定频率下的第一种控制方式是枚举运行时活跃SM数。每个候选并发数都要重新映射/调度，得到新duration、重叠与流量，再检查功率，选择可行者中的最快方案。不能事后把时延乘 `P/Pcap`，也不能把cap直接分给DP。较少核心可能减少瞬时功率，却延长base能耗，因此功率约束和能量目标分开。

## 5. 已实现的窄接口

[system_contract.py](system_contract.py) 提供：

- `quantization_work(rows, columns, target_format, recipe, ...)`：返回工作量、payload/scale、可省producer写回、source读取、launch和最小block临时空间。仅BF16→MXFP8/MXFP4；未提供未经校准的时延。权重展开使用独立转换事件，不冒充这个量化操作。
- `evaluate_power_windows(windows, profile, cap_w, boundary)`：输入明确窗口duration与事件计数、同一设计的J/event与base-W区间，输出逐窗口分项功率、总能量区间和准入状态。`required_event_keys`防止漏掉某个资源计数；不活跃也显式写0。该接口不自行生成时序、不模拟降频、不校准系数。

[system_power_template.json](configs/system_power_template.json) 的未知功率全部为null，不能直接生成“满足400W”的结论。`system_audit` 中仅有明确标记的人工代数例子用于接口演示，没有把它们用于芯片候选排名。

## 6. 可复现的系统资源观察与输出

```bash
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.system_audit \
  --output llmcompass_puzzle/runs/my-system-audit
python3.11 -m unittest discover -s llmcompass_puzzle/tests -p test_system_contract.py -v
```

输出：`area_fitted_resources.csv` 为27个配比/vector组合的安装资源上限；`resource_observations.json` 为面积组成、存储面积变化和roofline平衡点；`contract_examples.json` 为人工量化/功率例子；`manifest.json` 为输入/源码/输出hash。面积可安装上限不是最优性能结果，功率尚未参与这些候选排序。

本批观察及条件见 [运行记录](records/system-audit-20261113/README.md)。后续完整DSE每个候选需进一步输出总prefill时延、matrix/vector/转换/各层搬移服务与关键路径等待、内存峰值、安装/活跃SM、功率可行性、能量、淘汰原因、相对原始与优化基线的收益。

建议主图是**固定功率预算下的“迁移×配比”延时热图**，按vector/HBM或协同优化前后分面，遮罩不可行点；功率预算变化用多面板呈现，不把不同cap的候选放在同一排名。另画功率预算→最优配比/活跃SM和时延–能量Pareto，展示约束引起的选择变化。尚无完整时序前不填推理热图。

验证应覆盖量化的共享输入/尾部/metadata/融合流量守恒、相同工作量下功率与能量分离、HBM和L2容量边界、未参与参数拟合的GEMM/Norm/量化案例。对未知非DP功率和量化服务率进行成对敏感性与最坏后悔值分析；最佳配比只在声明区间内稳定时才称为稳健选择。

非DP校准最少需要四组证据：固定频率下的设备空闲/驻留基线；Norm、Softmax、block量化/pack微例的时间及增量能量；不同工作集的SRAM/L2/HBM流量微例；计算与搬移重叠的持出案例。减去同工况base后拟合J/work或J/byte区间，检查是否出现分项重复收费。校准数据与验证shape分开，记录设备、频率、功率采样窗口和不确定性；低采样率整卡功率不能证明短窗口峰值。A100只能校准其实际支持路径，改造后的多精度DP及N7漏电仍是独立代理，不继承A100误差数字。
