# Ascend Cube：计算分形、矩阵指令与软件 K 切分

调研日期：2026-10-24。状态：**资料核验与方案讨论，未批准阵列实现**。本轮没有运行 Ascend 编译器、反汇编、仿真器或设备实验；未新增 Chisel/RTL/testbench。主要对照 Atlas A2/A3 的 FP16 路径，不将新一代 Ascend 950 的布局或计算能力混入该例。

## 1. 结论与证据边界

Ascend FP16 的 16×16×16 描述基本 Cube 计算粒度，**不是一条 MMAD 的固定形状上限**。低阶 `Mmad`/`asc_mmad`/`mad` 可描述更大的 M/N/K。在合法的 L0 容量、布局、地址与同步条件下，128×128×128 可以作为一个矩阵指令块；软件不必发出 512 条 16×16×16 指令。

因此需要分开三个层次：

| 层次 | 表达内容 | 谁组织切分 |
| --- | --- | --- |
| 完整 GEMM / 高阶 Matmul | 任意更大矩阵、多核分配、片上缓存分块 | Kernel、库和编译器 |
| 低阶 MMAD | 已在 L0 的 M×K 与 K×N，相加到 L0C 的 M×N | 软件提供尺寸/地址，矩阵执行硬件完成该块 |
| FP16 Cube 基本计算 | 16×16×16 的算术工作量 | MMAD 以下的硬件执行 |

“单条矩阵指令包含 K 方向多个计算分形”与“软件沿 K 发多条矩阵指令”可以同时成立。低阶指令范围、物理计算粒度和完整 GEMM K 不应使用同一个 K 名称。

## 2. 为什么不是把高级 API 错当作一条指令

官方 `asc-devkit` 把 Basic API 定义为基于单指令抽象的接口，SIMD C API 定义为指令级透明映射，并与封装完整算法的高阶 API 分开。[官方 API 分层](https://gitcode.com/cann/asc-devkit)

`Mmad` 的参数表允许 m/n/k 分别取 0..4095，零尺寸不执行；这只是参数编码范围，**不保证任意三元组都能放入实际 L0**。官方还以 FP16 M30K70N40 说明 A/B/C 分别覆盖 2×5、5×3、2×3 个 16×16 分形，表明其计算范围并不局限于一个分形。[Mmad 参数与尾部示例](https://www.hiascend.com/document/detail/en/CANNCommunityEdition/910/API/ascendcopapi/docs/en/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute/Mmad.md)

更低层的 `asc_mmad` 在架构 2201 原型中直接接收 `m,k,n`；官方 CCE intrinsic `mad` 也直接描述 A(m×k)、B(k×n)、C(m×n)。这些资料与单指令 API 分层相互印证，不能仅以高阶 `Matmul::Iterate` 的形状替代。[asc_mmad 原型](https://asc.gitcode.com/api/SIMD-API/c_api/cube_compute/mmad_compute/asc_mmad.html)、[CCE mad](https://www.hiascend.com/document/detail/zh/canncommercial/850/API/cceintrinsicapi/cceapi_0063.html)

这里核实的是公开的指令接口合同；没有自行检查 A2/A3 编译产物，不能宣称所有版本、类型和包装调用都恰好编译成同样数量的机器指令。

## 3. M128N128K128 的分解

先考虑一份单核低阶矩阵命令，A/B 为 FP16、C/累加结果为 FP32。若数据及其他同时存活的 buffer 满足该设备的 L0 约束，可以选择 `m=128,n=128,k=128`：

- A 的有效载荷：128×128×2 = 32 KiB。
- B 的有效载荷：128×128×2 = 32 KiB。
- C/结果的有效载荷：128×128×4 = 64 KiB。

这些是本例数据量计算，不是芯片存储容量规格；双缓冲、对齐、其他张量和端口需求另计。

设 `i,j,p=0..7`，各 A/B 子块均为16×16，则数学关系为：

`D[i,j] = C[i,j] + Σ(p=0..7) A[i,p] × B[p,j]`。

因此：

| 项目 | 数量 |
| --- | ---: |
| M 方向输出分形 | 128/16 = 8 |
| N 方向输出分形 | 128/16 = 8 |
| 独立的16×16输出分形 | 8×8 = 64 |
| 每个输出覆盖的K16区间 | 128/16 = 8 |
| 基本Cube乘加工作量 | 64×8 = 512 |
| 总MAC | 128³ = 2,097,152 |

这是数学分解，不是已知的逐拍 `for m → for n → for k` 顺序，也不规定中间舍入或内部 accumulator 的物理位置。

华为的 FP16 性能优化示例直接比较 base 块 128×256×64 与 128×128×128，并按每周期16³计算能力得到两者均为512个纯计算周期的模型。[官方基本块性能算例](https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/82RC1alpha001/opdevg/ascendcbestP/atlas_ascendc_best_practices_10_0027.html)

512 是该吞吐假设下的算术工作量/峰值吞吐模型，不是我们实测的单条指令完成延迟。L0就绪等待、指令启动、流水尾部、搬运和同步需要另外计入，不能拿它直接作为端到端 GEMM latency。

## 4. 单条指令内部能确认哪些调度机制

官方 `SetMMLayoutTransform` 可控制先沿 N 再沿 M，或先沿 M 再沿 N 产生输出。这证明矩阵指令内部存在可配置的输出遍历，**没有公开其完整 K/M/N 每拍调度表**。[A2/A3 遍历方向接口](https://www.hiascend.com/doc_center/source/en/canncommercial/850/API/ascendcopapi/atlasascendc_api_07_0260.html)

UnitFlag 在 L0C 以512 B内存块管理读写状态，使计算与结果搬出能够按块协调。官方最佳实践说明，启用该功能时，单条 MMAD 执行中已完成的512 B结果可供 FIXPIPE 搬出，无须用一个整条指令 busy 位阻塞所有输出。[UnitFlag 机制](https://www.hiascend.com/document/detail/en/CANNCommunityEdition/910/API/ascendcopapi/docs/en/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute_key_features/UnitFlag.md)、[计算与搬出重叠](https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/910beta3/programug/Ascendcopdevg/docs/guide/算子实践参考/优秀实践/Matmul性能调优案例/Matmul高阶API使能UnitFlag.md)

512 B 是同步块大小，不能与一个 FP32 16×16 输出分形的1024 B混为一谈。也不能由 L0C 对软件可见就断定每个 K16 步都读写一次 L0C；内部寄存器、旁路、写回粒度尚需微基准或更直接资料。

## 5. 更大 K 的软件切分仍然存在

官方 UnitFlag 示例为 A(128×1024)×B(1024×128)，选择每条 MMAD 的 K=128，软件循环8次，最后一次 Fixpipe 搬出结果。前7次保持 L0C 的计算占用状态，最后一次允许结果消费。这是**8条K128指令**，不是软件必须生成64条K16指令。[官方跨指令示例](https://www.hiascend.com/document/detail/en/CANNCommunityEdition/910/API/ascendcopapi/docs/en/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute_key_features/UnitFlag.md)

相邻指令更新同一 L0C 还存在累加 RAW。官方 Mmad 文档对较小 M/N 指出需要 `PIPE_M` 同步；这个现象可支持本项目分析“独立输出数与反馈延迟”的关系，但其阈值不能移植到我们的18拍浮点核心。[Mmad 同步约束](https://www.hiascend.com/document/detail/en/CANNCommunityEdition/910/API/ascendcopapi/docs/en/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute/Mmad.md)

软件也可以因双缓冲、带宽或实际存储容量，把128³改成多个更小 MMAD 块。例如两条 K64 指令按同一输出累加；这是一种合法的调度选择，不是16³计算粒度强迫软件采用的唯一方案。

## 6. 与 NVIDIA 及本项目的边界比较

| 项目 | NVIDIA 选定的固定shape MMA | Ascend A2/A3 FP16 MMAD | 本项目原生K候选 |
| --- | --- | --- | --- |
| 指令K | 取决于具体opcode/shape，例如16 | 尺寸参数可大于16，例如128 | 绑定配置/模式的完整点积容量 |
| 基本计算粒度与指令K | PTX不直接公开物理执行对应关系 | 16³基本能力与更大MMAD块明确分层 | 由我们自己的PE/K-PE规格定义 |
| 大GEMM的K | 软件组织多条MMA | 软件组织多条较大MMAD | 软件组织多条原生指令 |
| 指令内时间K步骤 | 不能仅由PTX形状判定 | 大于K16的矩阵指令需硬件完成多个基本计算分形 | 候选约束为不重复完整PE+C/D路径来拼K |

NVIDIA的16/32/64不是跨所有指令族的通用常数；CUTLASS的软件K循环与PTX指令内部实现也应分开。[PTX](https://docs.nvidia.com/cuda/parallel-thread-execution/)、[CUTLASS GEMM分层](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/gemm_api_3x.html)

本项目目前应保留两个可讨论的接口选择：

1. **原生K指令**：例如E192提供K192，一条指令内部只展开M/N；较长GEMM由软件生成序列。控制简单，适合隔离原生K宽度与配比的影响。
2. **可变K矩阵指令**：例如E64接受K192，指令执行器负责三个原生K更新；软件仍对超过缓存容量的更大GEMM分块。需增加指令内K计数、反馈依赖、scale寻址和数值合同。

两者都是可选的设计边界；不因Ascend采用更大矩阵指令就自动改变本项目实现。尤其要区分“扩大原生空间K会减少完整C/D处理次数”与“把相同的多次更新从软件命令移到硬件内部”：后者本身不保证减少算术量、舍入次数或L0访问。若内部累加器/缓冲改变，这些收益与成本应独立计量。

下一轮审核应决定指令K边界，以及部分和驻留、跨指令依赖、scale布局与完成协议。此前不写阵列代码。
