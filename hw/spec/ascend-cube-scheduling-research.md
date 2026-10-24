# Ascend Cube：计算分形、矩阵指令与软件 K 切分

调研日期：2026-10-24。状态：**资料核验与方案讨论，未批准阵列实现**。本轮阅读了官方机器码解码/插桩源码、算子库源码镜像和第三方公开的指令级 simulator 工件；没有自行运行 Ascend 编译器、反汇编、仿真器或设备实验。未新增 Chisel/RTL/testbench。主要对照 A2/C220 的 FP16 路径，不将新一代 Ascend 950 的布局或计算能力混入该例。

## 1. 结论与证据边界

Ascend FP16 的 16×16×16 描述基本 Cube 计算粒度，**不是一条 MMAD 的固定形状上限**。这次追查到机器指令层：官方 A2 解码表识别 `MMAD f16_to_f32`，其 M/K/N 来自配置寄存器的三个 12-bit 字段。公开 C220 仿真工件中，FP16 M32N32K32 对应一次 MMAD 动态执行，直接排除了“底层只能 K16”及“底层只能固定 K128”的说法。

指令接口采用可配置 M/N/K，而不是只枚举一个固定的 K128。K128 属于可描述的尺寸，是否能在给定 M/N 下执行还受 L0 容量、布局、地址和同步约束；本轮没有重跑 K64/K128/K256 的编译和执行对照。下面将源码合同、机器编码、已发布指令记录和数学推演分别标明。

因此需要分开三个层次：

| 层次 | 表达内容 | 谁组织切分 |
| --- | --- | --- |
| 完整 GEMM / 高阶 Matmul | 任意更大矩阵、多核分配、片上缓存分块 | Kernel、库和编译器 |
| 机器 MMAD | 已在 L0 的 M×K 与 K×N，相加到 L0C 的 M×N | 软件配置尺寸/地址，矩阵执行硬件完成该块 |
| FP16 Cube 基本计算 | 16×16×16 的算术工作量 | MMAD 以下的硬件执行 |

“单条矩阵指令包含 K 方向多个计算分形”与“软件沿 K 发多条矩阵指令”可以同时成立。低阶指令范围、物理计算粒度和完整 GEMM K 不应使用同一个 K 名称。

## 2. 从算子库追到机器 MMAD

API 接收可变 K，不能单独证明它只发一条计算指令。以下证据分别检查调用路径、机器 opcode、配置位段和动态指令次数；不以 `Matmul::Iterate` 或 C++ 函数调用次数代替机器指令次数。

### 2.1 算子库最底层如何调用

阅读 `asc-devkit` 的 C220 路径，调用关系为：

```text
AscendC::Mmad(dst, a, b, params)
  → MmadImpl：检查并取得 L0C/L0A/L0B 物理地址
  → MmadCal：选择类型、形成 C 初始化标志
  → mad(c, a, b, m, k, n, 控制标志...)
```

这是对真实源码的精简表示，不是可直接编译的函数原型。`__NPU_ARCH__ == 2201` 选择 `dav_c220`；FP16→FP32 分支把原始 `m/k/n` 传给一次 `mad`，这几层没有把 K 除以16再循环调用 `mad`。地址空间 `__cc__`、`__ca__`、`__cb__` 分别对应 C、A、B 的专用片上存储。源码保留初始化/累加与 UnitFlag 等控制参数，不能只看三个尺寸而忽略它们。

本次可访问的是 `hicann/asc-devkit` 源码镜像，固定 commit `56500ea0dc219380f50f4a17ce73ef5264f830fc`，不是声称在官方站点重新编译了该库：[Mmad 入口](https://github.com/hicann/asc-devkit/blob/56500ea0dc219380f50f4a17ce73ef5264f830fc/impl/basic_api/kernel_operator_mm_intf_impl.h#L444)、[MmadImpl 与地址提取](https://github.com/hicann/asc-devkit/blob/56500ea0dc219380f50f4a17ce73ef5264f830fc/impl/basic_api/kernel_operator_mm_base_impl.h#L486)、[C220 MmadCal 的 mad 调用](https://github.com/hicann/asc-devkit/blob/56500ea0dc219380f50f4a17ce73ef5264f830fc/impl/basic_api/dav_c220/kernel_operator_mm_impl.h#L367)。镜像版本与下面 CANN 8.5.0 的 trace 不是同一次构建，不能混称为完整重建的编译链。

更低层的 CANN 8.1.RC1 编译器头文件也明确将这一路命名为 v220 MMAD instruction，描述 XT/XD 的寄存器控制；其中 bias wrapper 只拼接地址，然后调用 `mad` 的配置字或 m/k/n 重载。本次没有取得编译器后端 lowering 源码，不虚构其 builtin 符号或内部微操作。[SDK 编译器头文件镜像，固定版本](https://github.com/leideng/CANN-8.1.RC1/blob/551ed27c29284929bbdc2239e929ddfedfdf0b8b/Ascend/ascend-toolkit/8.1.RC1/aarch64-linux/ccec_compiler/lib/clang/15.0.5/include/__clang_cce_aicore_functions.h#L2285)

### 2.2 确认它是机器指令，以及 M/N/K 的位置

官方 `Ascend/msopprof` 从 ELF `.text` 读取机器码，给 910B/910_93 系列选择 A2 表，并按 mask 匹配指令类型。Cube mask 为 `0xefc00001`，其中解码键 `0xe0c00000` 对应 `MMAD f16_to_f32`。这是机器 opcode 分类，不是源代码 API 名称；解码键也不是上述例子完整的机器指令字。[ELF 解码流程](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/csrc/op_profiling/instr_encoding/instr_encoding.cpp)、[A2 Cube opcode 表](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/csrc/op_profiling/instr_encoding/encodingA2/CubeInstrTableA2.h#L29)、[解码 mask](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/csrc/op_profiling/instr_encoding/instr_encoding.h)

官方 `Ascend/mssanitizer` 为旧代 `mad` 提供 FP16→FP32 插桩入口，并用 `ParseMadConfig` 读取配置：

| 参数 | 64-bit config / XT 中的位段 |
| --- | --- |
| M | `[11:0]` |
| K | `[23:12]` |
| N | `[35:24]` |
| 初始化、累加来源等控制 | 更高位，具体定义见源码 |

所以，K 是传入矩阵计算指令的长度参数，不是 opcode 中固定为16或128的常量。12-bit 字段说明编码范围；**不能仅凭字段宽度断言任意1..4095及任意 M/N 组合都合法、都装得进 L0**。[FP16 mad 插桩入口](https://github.com/Ascend/mssanitizer/blob/78037658773f27796624148ce7680ccb9e24ae66/csrc/plugin/ccec/calc_instructions/mad.cpp#L79)、[M/K/N 位段定义](https://github.com/Ascend/mssanitizer/blob/78037658773f27796624148ce7680ccb9e24ae66/csrc/plugin/record_calc_instructions.h#L1006)

该插桩的访存检查另按 FP16 `k0=256/16=16`、`ceil(K/16)` 计算分形数。这同时保留了“指令长度 K”和“存储分形 K16”两个量；访存检查源码不能用来断言实际逐拍执行顺序。[分形访存范围计算](https://github.com/Ascend/mssanitizer/blob/78037658773f27796624148ce7680ccb9e24ae66/csrc/plugin/record_calc_instructions.h#L1034)

### 2.3 一个实际发布的例子：M32N32K32 只执行一次 MMAD

第三方仓库 `rainbay001-dotcom/triton` 的公开工件，固定 commit `0ebd8c7037f2ace93e7bddd01bc3d20e5215cf5b`，包含 FP16 A/B、FP32 C 的 M32N32K32 kernel 及 simulator 输出。流程为 GM → L1 → L0A/L0B → MMAD → L0C → Fixpipe → GM；整个 kernel 还有搬运、标量配置和同步指令，不能说整个 kernel 只有一条指令。[尺寸设置](https://github.com/rainbay001-dotcom/triton/blob/0ebd8c7037f2ace93e7bddd01bc3d20e5215cf5b/kernels/mmad_sample/mmad_custom_cube_only.h#L166)、[Compute](https://github.com/rainbay001-dotcom/triton/blob/0ebd8c7037f2ace93e7bddd01bc3d20e5215cf5b/kernels/mmad_sample/mmad_custom_cube_only.h#L125)

`core0.cubecore0_instr_exe.csv` 只有一条 MMAD 记录，关键字段摘录如下；省略周期数据，避免将第三方 simulator 数字用作本项目硬件性能证据：

```text
instr      = MMAD
addr       = 282122692 = 0x10d0d9c4
pipe       = CUBE
call_count = 1
dtype      = F16F32
XT         = 0x8000000020020020
```

按官方位段解码，`M=32, K=32, N=32`。同一工件的 `trace.json` 也只有一个 MMAD 事件，PC/XT 一致，源码映射经过 CANN 8.5.0 的 `dav_c220/kernel_operator_mm_impl.h:333` 到示例 `Compute` 的第134行。因此该例是**一次机器 MMAD 覆盖 K32**，没有在软件中拆成两次 K16 MMAD。[原始指令记录](https://github.com/rainbay001-dotcom/triton/blob/0ebd8c7037f2ace93e7bddd01bc3d20e5215cf5b/profiling/mmad_sim_20260411_050738/simulator/core0.cubecore0/core0.cubecore0_instr_exe.csv#L120)、[原始 trace](https://github.com/rainbay001-dotcom/triton/blob/0ebd8c7037f2ace93e7bddd01bc3d20e5215cf5b/profiling/mmad_sim_20260411_050738/simulator/core0.cubecore0/trace.json)

这里的 `call_count=1` 是机器指令执行次数。官方工具文档将 `*_instr_exe.csv` 定义为指令级数据，`addr` 是 PC；另一个 `*_code_exe.csv` 才按源代码行归集指令次数，二者不能混用。[官方记录格式](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/docs/en/user_guide/msopprof_simulator_performance_data.md#L53)

**证据限制：**此工件不是本项目重跑结果，没有拿到该样例的 ELF/机器码 dump；能确认 CANN 8.5.0 / dav_c220 路径，不能确定具体 SKU，也不能据此给出真实硬件时延。可变尺寸的编码、库调用与单条 K32 记录相互支持；完整合法形状集合及内部微操作序列仍需厂商合同或受控实验。

### 2.4 API 文档只作为补充合同

`Mmad` 文档允许 m/n/k 分别取0..4095，零尺寸不执行，并以 FP16 M30K70N40 说明尾部分形。`asc_mmad` 在架构2201也直接接收 m/k/n；这些是接口合同的补充证据，不代替上述机器层检查。[Mmad 参数与尾部示例](https://www.hiascend.com/document/detail/en/CANNCommunityEdition/910/API/ascendcopapi/docs/en/api/SIMD-API/basic_api/cube_compute_ISASI/mmad_compute/Mmad.md)、[asc_mmad 原型](https://asc.gitcode.com/api/SIMD-API/c_api/cube_compute/mmad_compute/asc_mmad.html)

更低层的 CCE intrinsic `mad` 文档同样列出 FP16→FP32 的 m/k/n 原型及0..4095元素的参数范围；任一维为零视为 NOP。因此 K64/K128/K256 在该底层接口允许的参数范围内，完整形状仍要满足存储与其他约束。检索时读取到了官方参数表，但该旧版链接直接打开有时会跳转到文档首页；机器层结论还由上述固定版本源码和指令记录独立支持。[CCE mad 低层定义](https://www.hiascend.com/document/detail/zh/canncommercial/850/API/cceintrinsicapi/cceapi_0063.html)

## 3. M128N128K128 的分解

以下是接口合同下的单核矩阵命令分析，不是本轮获得的 K128 指令 trace。A/B 为 FP16、C/累加结果为 FP32；若数据及其他同时存活的 buffer 满足该设备的 L0 约束，可以选择 `m=128,n=128,k=128`：

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

NVIDIA的16/32/64不是跨所有指令族的通用常数；CUTLASS的软件K循环与PTX指令内部实现也应分开。PTX 本身是虚拟 ISA，严格对比机器指令边界时还要检查目标架构的 SASS，不能仅凭一条 PTX 写法保证唯一的机器指令映射。[PTX](https://docs.nvidia.com/cuda/parallel-thread-execution/)、[CUTLASS GEMM分层](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/gemm_api_3x.html)

本项目目前应保留两个可讨论的接口选择：

1. **原生K指令**：例如E192提供K192，一条指令内部只展开M/N；较长GEMM由软件生成序列。控制简单，适合隔离原生K宽度与配比的影响。
2. **可变K矩阵指令**：例如E64接受K192，指令执行器负责三个原生K更新；软件仍对超过缓存容量的更大GEMM分块。需增加指令内K计数、反馈依赖、scale寻址和数值合同。

两者都是可选的设计边界；不因Ascend采用更大矩阵指令就自动改变本项目实现。尤其要区分“扩大原生空间K会减少完整C/D处理次数”与“把相同的多次更新从软件命令移到硬件内部”：后者本身不保证减少算术量、舍入次数或L0访问。若内部累加器/缓冲改变，这些收益与成本应独立计量。

下一轮审核应决定指令K边界，以及部分和驻留、跨指令依赖、scale布局与完成协议。此前不写阵列代码。
