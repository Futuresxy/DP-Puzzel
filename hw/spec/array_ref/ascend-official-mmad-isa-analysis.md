# 官方 Ascend C：从矩阵乘样例到 MMAD 机器指令

核验日期：2026-10-24。对象：A2/A3 的 `dav-c220-cube`，FP16 输入、FP32 累加。本文使用官方 GitCode 源码及从华为官方 Toolkit 提取的编译器，替代此前依赖源码镜像、第三方 trace 的主证据。阵列方案仍待审核。

## 1. 先说明本次实际完成了什么

- 直接克隆 `https://gitcode.com/cann/asc-devkit.git`，固定官方标签 `v9.1.0`、commit `e5451c7feba11f9e259f4fbc19c4bf82f8c0496c`，阅读其矩阵乘样例、Basic/C API 实现、参数和存储约束。
- 从官方 CANN 9.1.0 Toolkit 流式提取 BiSheng 编译器与 Ascend C 组件，不运行安装器、不安装驱动；组件保存在被忽略的 `.deps/`。版本和 hash 见 [依赖记录](../../../dependencies/ascend-research.json)。
- 用官方 Basic API 编译16个 FP16 形状探针，检查 LLVM IR、设备 ELF `.text` 的机器指令字和后端汇编。源码调用次数与机器指令次数分别核对。
- **没有运行这些设备 kernel、数值仿真或真实芯片实验。**探针没有初始化 L0，不能执行，更不能用其结果声称数值正确或测得硬件时延。

本轮的“生成一条 MMAD”指静态机器码结论；指令内部的微操作、流水和每拍 K 调度不由该计数给出。

## 2. 贯穿实例：官方 M256N256K64

官方文件为 `examples/01_simd_cpp_api/00_introduction/02_matrix/matmul_basic_api/matmul_basic_api.asc`。主函数给出 `M=256,K=64,N=256`，启动两个 Cube 核；每核负责 `baseM=128,baseN=256,baseK=64`。输入为 FP16，L0C 累加为 FP32，Fixpipe 将结果转为 FP16 写回 GM。

[官方样例尺寸与启动配置](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/examples/01_simd_cpp_api/00_introduction/02_matrix/matmul_basic_api/matmul_basic_api.asc#L105)

每核的数据过程是：

```mermaid
flowchart LR
    G["GM: A的128行与完整B"] --> L["L1: ND转Nz"]
    L --> A["L0A: A128×64, Zz"]
    L --> B["L0B: B64×256, Zn"]
    A --> M["矩阵计算: M128N256K64"]
    B --> M
    M --> C["L0C: FP32 128×256"]
    C --> F["Fixpipe: 转FP16并写GM"]
```

单核占用分别为 A=16 KiB、B=32 KiB、L0C=128 KiB。样例中的 M/K 循环位于 `LoadData`，组织 L1→L0 的分形搬运；不能把这些搬运循环当作多次 K16 计算。MTE2→MTE1、MTE1→M、M→FIX 的事件分别保证搬入、计算与搬出的数据依赖。

第91行的 `Mmad` 使用完整 `baseM/baseN/baseK`，且 C 初始化标志为 true，本例计算 C=AB。若读取已有 L0C 作为初值，则是矩阵乘累加语义。**这一处只有一个 API 调用，尚不足以单独证明只有一个机器计算指令。**

[官方搬运、同步与 Mmad 调用](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/examples/01_simd_cpp_api/00_introduction/02_matrix/matmul_basic_api/matmul_basic_api.asc#L38)

## 3. 从公开类库到编译器入口

固定官方 commit 中的调用链为：

| 层次 | 位置 | 对这份 FP16 形状做什么 |
| --- | --- | --- |
| `Mmad` | `impl/basic_api/kernel_operator_mm_intf_impl.h:371` | 将参数传入 `MmadImpl` |
| `MmadImpl` | `impl/basic_api/kernel_operator_mm_base_impl.h:446` | 取得 L0C/L0A/L0B 物理地址，调用 `MmadCal` |
| 代际选择 | 同文件第31行 | 架构2201选择 `dav_c220` |
| `MmadCal` | `impl/basic_api/dav_c220/kernel_operator_mm_impl.h:340` | FP16→FP32 分支将原始 m/k/n 传给 `mad` |

这几层没有把 K 除以16后循环发出 `mad`；这仍是库结构事实，最终指令数量由下一节的编译产物确认。

[官方 Mmad](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/impl/basic_api/kernel_operator_mm_intf_impl.h#L371)、[官方公共实现](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/impl/basic_api/kernel_operator_mm_base_impl.h#L446)、[官方 C220 最底层调用](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/impl/basic_api/dav_c220/kernel_operator_mm_impl.h#L340)

官方 C API 的 FP16 路径也直接调用同一 `mad`，见 `impl/c_api/instr_impl/npu_arch_2201/cube_compute_impl/asc_mmad_impl.h:64`。本地官方编译器包中的 `cce_aicore_intrinsics.h` 则以 `clang_builtin_alias(__builtin_cce_mad)` 声明 `mad`。这里确实进入编译器内建接口，而不是又找到一个封装完整 GEMM 的 C++ 算法。

[官方 C API 到 mad](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/impl/c_api/instr_impl/npu_arch_2201/cube_compute_impl/asc_mmad_impl.h#L64)

## 4. 真正编译：API → LLVM IR → MMAD 机器码

最小探针保留官方 Basic API 的 LocalTensor 和 Mmad 路径，只删除 GM 搬运、host 启动等无关部分。它不是完整 GEMM kernel；目的是隔离一个给定形状的矩阵计算调用，检查是否被拆为多条 Cube 指令。可复现源码为 [ascend_mmad_probe.cpp](../../../scripts/research/ascend_mmad_probe.cpp)，检查入口为 [inspect_ascend_mmad.py](../../../scripts/research/inspect_ascend_mmad.py)。

实际编译使用官方 CANN9.1.0 配套 release 头文件，`Mmad`、`MmadImpl`、C220 `MmadCal` 三个关键实现文件与官方 v9.1.0 标签逐字节相同，SHA-256 记录在依赖清单。另尝试将同一探针用于官方 master `4b40fcab44231e32d565adafdf8efbc41b603914`，但9.1.0编译器不能识别其新增 FP4/FP8 类型，编译失败；未改写第三方头文件来绕过。故不能宣称最新 master 已用旧工具链构建通过，下面的机器码结论限定于已固定的官方9.1.0组合。

目标固定为 `--cce-aicore-arch=dav-c220-cube`，使用 C++17、O2。BiSheng 版本字符串包含 `clang-5c68a1cb1231`，构建时间为2026-07-30。编译对象、bitcode、LLVM IR、汇编和日志保存在 `.cache/ascend-official/`，小型检查摘要另行版本化。

M128N128K128 的 LLVM IR 含一次 `llvm.hivm.MAD.f162f32`，其配置数按无符号解释为 `0x8000000080080080`。这里的 IR 仍非机器指令，所以继续检查 ELF 与后端输出。机器码按官方 A2 解码 mask `0xefc00001`、key `0xe0c00000` 分类，找到一个 FP16→FP32 MMAD 指令字 `0xf0c21080`。

[官方 ELF 机器码解码流程](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/csrc/op_profiling/instr_encoding/instr_encoding.cpp)、[官方 A2 MMAD 解码表](https://github.com/Ascend/msopprof/blob/a52c8694979016be703006ec242901519bef31d8/csrc/op_profiling/instr_encoding/encodingA2/CubeInstrTableA2.h#L29)

官方工具包的 `llvm-objdump` 在本机对该 ELF 显示 `<not available>`，因此不把它冒充可读反汇编。检查脚本使用官方编译器后端输出汇编，保留原驱动的 target/LLVM 选项，并确认从同一 bitcode 回到机器码后，`.text` 与原驱动产物**逐字节一致**。这使汇编分析能够回溯到已核对的机器指令字，而非手写伪汇编。

M128N128K128 的真实后端汇编关键段如下：

```asm
MOV             X0, #128
MOVK            X0, #32776, #1
MOVK            X0, #32768, #3
MOV             X1, #0
MOV             X15, #0
MMAD.f162f32    [X1], [X1], [X1], X0
```

`MOVK` 将16-bit片段填入指定位置，得到 X0=`0x8000000080080080`。三个地址虽都为0，却属于 L0C、L0A、L0B 三个不同地址空间。矩阵操作数地址与尺寸配置共同定义该条机器指令的负载，不能将助记符的操作数个数理解为矩阵固定形状。

官方 `ParseMadConfig` 明确给出 M=`config[11:0]`、K=`config[23:12]`、N=`config[35:24]`；本例均解码为128。bit63控制 C 初值为零。其计算语义覆盖 M×N 个输出，每个输出具有长度 K 的归约；它没有要求软件在这条指令之外先拆成八条 K16 指令。

[官方配置位段定义](https://github.com/Ascend/mssanitizer/blob/78037658773f27796624148ce7680ccb9e24ae66/csrc/plugin/record_calc_instructions.h#L1006)

## 5. 单条指令最大 size 的正确表达

同版本官方 C API 文档规定 M/K/N 的参数范围均为0..4095，任一为零为 NOP。A2/A3 的 L0A、L0B 各64 KiB，L0C为128 KiB。它们是**三个独立的容量约束**，不是允许同时执行4095³的承诺。

[官方v9.1.0参数定义，第108行起](https://gitcode.com/cann/asc-devkit/blob/e5451c7feba11f9e259f4fbc19c4bf82f8c0496c/docs/api/SIMD-API/C-API/cube_compute/asc_mmad.md#L108)、[官方 A2/A3 容量约束，第272行起](https://gitcode.com/cann/asc-devkit/blob/4b40fcab44231e32d565adafdf8efbc41b603914/docs/zh/api/SIMD-API/c_api/cube_compute/mmad_compute/asc_mmad.md#L272)

对普通稠密 FP16→FP32 路径，设 `M16=ceil(M/16)*16`，N16、K16同理；矩阵起始地址为0、不与其他存活张量共享空间时，容量要求为：

```text
2 × M16 × K16 ≤ 65,536 B
2 × K16 × N16 ≤ 65,536 B
4 × M16 × N16 ≤ 131,072 B
```

分形与位宽依据为官方文档的 K0=`32 B/sizeof(dtype)`，以及官方 FP16 性能探针中的补齐计算。该推导不覆盖特殊 GEMV、稀疏、不同数据类型或多 buffer 共存情形。

[官方分形定义](https://gitcode.com/cann/asc-devkit/blob/4b40fcab44231e32d565adafdf8efbc41b603914/docs/zh/api/SIMD-API/c_api/cube_compute/mmad_compute/asc_mmad.md#L53)、[官方补齐计算](https://gitcode.com/cann/asc-devkit/blob/4b40fcab44231e32d565adafdf8efbc41b603914/tests/perf/mmad_perf/mmad_perf.asc#L61)

因此，最大负载应当表达为一组受约束的 M/N/K，而不是一个固定三元组：

| 条件 | 由官方约束推导的边界 | 含义 |
| --- | --- | --- |
| 固定 M=N=128 | K≤256 | K256 时 A/B 各64 KiB，C为64 KiB |
| 固定 M128、N256 | K≤128 | B与C先达到容量边界 |
| 固定 M=N=16 | K≤2048 | K2048 时 A/B各64 KiB，C为1 KiB |
| M=N=K，按16对齐 | 最大为176³ | 192³超出A/B/C容量；176³仅是容量和参数合同下的最大方块 |
| 同时保留两份同尺寸 A/B、M=N=128 | 每份K≤128 | 这是双 buffer 的资源约束，不是指令K固定128 |

补充核对的官方master `4b40fcab44231e32d565adafdf8efbc41b603914` 中，`tests/perf/mmad_perf/perf.sh:103` 的 A2 FP16 场景明确扫描 M/N=128、K=128/256，并注明 K256 占满 L0A/L0B，与上述计算一致。本轮没有执行该性能脚本，它不是本项目测得的硬件结果。

[官方 FP16 扫描与容量边界](https://gitcode.com/cann/asc-devkit/blob/4b40fcab44231e32d565adafdf8efbc41b603914/tests/perf/mmad_perf/perf.sh#L103)

## 6. 编译成功还不能证明硬件形状合法

16个探针包含合法候选和故意越界的对照。可检查的要点是：

- M128N128 的 K16/32/64/96/128/192/256 均生成一次 MMAD，且配置字段保留所请求形状。
- M128N128K257 等超 L0 形状仍能编译为一次 MMAD；必须由容量检查排除，不能把“编译器接受”写成“芯片支持”。
- K4096 超出12-bit合同，本次编译器仍接受，实际编码的K变成0。该对照直接说明仅统计一次机器指令也不够，还必须检查操作数字段。
- M16N16K2048 和176³各生成一次 MMAD，并满足这里检查的容量/尺寸条件；它们尚不是实机验收结果。

每个可编译案例同时记录机器字、IR配置、汇编行、文件hash、容量判断，以及后端和原始 `.text` 是否一致。见[16个编译探针摘要](../../../docs/research/ascend-mmad-isa/compile-summary.json)和[复现说明](../../../scripts/research/README.md)。实际参与编译的官方9.1.0 release中，三个关键实现文件已与官方Git标签v9.1.0做逐字节和SHA-256核对。所有越界探针只编译，不执行。

## 7. 对本项目的含义与尚未揭示的硬件

已有证据支持：这一路机器 ISA 用可变 M/N/K 指定一个矩阵计算块，FP16 的基本 K16 粒度可以位于一条更大 MMAD 的内部。它为“软件提交较大矩阵命令、硬件组织内部计算”提供了官方参照。

证据没有揭示每个 K16 分段的逐拍顺序、内部累加寄存器、每段是否访问 L0C、舍入发生位置或完整反馈流水。`128/16=8` 只给出算术分段数，不能直接推出八周期。对本项目原生K接口与可变K执行器的取舍，仍需用户审核，不能据此自动添加阵列代码。
