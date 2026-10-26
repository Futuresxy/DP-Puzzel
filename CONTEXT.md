# 多精度张量计算配比

本项目研究 AI 芯片中不同精度张量算力的配置与实现，及其面积、功耗和负载延迟的权衡。

## Language

**数值格式（Numeric Format）**：共同定义元素编码、共享缩放、累加、舍入及特殊值语义的一组规则。相同元素位宽不代表相同数值格式。
_Avoid_: 以“4 bit”“低精度”代替完整格式

**精度族（Precision Family）**：用于分析的格式分组，如 BF16/FP16、MXFP8/6、MXFP4/NVFP4/HiF4。分组不表示组内硬件成本或数值行为相同。

**H/Q/E 容量（HQE Capacity）**：H=half、Q=quarter、E=eighth 家族每次接收可处理的实际 K 元素数，例如 H16Q32E64。Q 包含 FP8/FP6，E 包含 MX/NV/HiF4；共享模式的三项容量不能同时相加。

**基础PE**：原MidGroup边界。五族H/Q/E/HQE/QE共六profile，g表示PEGroup数；H/Q/HQE/QE为g4，E为g4/g2。H16/Q32采用一次全局对齐，HQE/QE/E保留分级组织。六种PE均输出扩展精度sign/magnitude/anchor结果，S11、F=pe_align_width。

**PEGroup / SubPE**：HQE/QE/E基础PE内保留的实际模块，每PG四SubPE；HQE/QE按模式分别处理每word一个H、两个Q或四个E元素。H/Q专用PE已经取消这些模块，16/32路解包、乘法、全K对齐和累加直接展开在PE_H.scala/PE_Q.scala。其g4名称只保留输入布局兼容性。

**K-PE**：1–4个基础PE沿K空间规约，共享一个C/D，模式native K为活动实例容量之和；输入物理槽不隐式压缩。

**MN-PE**：一个基础PE及独立C/D，代表一个M/N输出位置；当前不包含阵列。K/MN均18级、batch固定模式。

**对齐窗口**：生成时参数，默认Q字内28、PG guard2、PE40、PE+C40；公开范围和传递以config/Parameters.scala为准。乘加自然增长，统一输出坐标不等于不同RTZ组织的误差相同。

**指令 K（Instruction K）**：一条 MMA 指令在语义上覆盖的归约长度；不同于完整 GEMM 的 K，也不单独规定物理执行周期。

**原生 K（Native K）**：指定配置和模式下，一个输出计算单元一次事务覆盖的点积长度。
_Avoid_: 将原生 K 等同于单周期完成，或由 PTX 形状反推乘法器数量

**输出子块（Output Microtile）**：一条逻辑指令在 M/N 方向映射到物理输出位置的一部分，各子块具有独立的输出坐标。

**跨指令 K 累加（Inter-instruction K Accumulation）**：多条 MMA 指令覆盖同一输出的不同 K 区间，并以前一条结果作为后一条的 C。
_Avoid_: 与 K-PE 内部的空间规约、单条指令内部的时分 K 混用

**硬件实现（Hardware Implementation）**：具有确定资源组织和时序行为的物理计算单元设计。一个实现可以支持一个或多个数值模式。

**运行模式（Operating Mode）**：一个硬件实现在一次计算期间采用的数值与资源使用方式。共享物理资源的互斥模式不能同时贡献其各自峰值算力。

**计算阵列（Compute Array）**：由多个点积处理单元组成、按规定数据流协同执行张量计算的单元。
_Avoid_: 将阵列与整芯片混用

**计算核心（Compute Core）**：包含一个或多个计算阵列及相应局部存储、控制资源的计算资源单元。可参照 SM/AICore 的组织层级，但不等同于其全部厂商功能。

**芯片配置（Chip Configuration）**：计算核心、阵列、存储和共享资源的完整组织及运行条件。

**物理资源配比（Physical Allocation）**：不同硬件实现的实例数量或面积分配比例。
_Avoid_: 与运行模式的使用时间占比混用

**算力配比（Compute Ratio）**：在明确并发可行性与数值语义下，各精度模式可提供的峰值计算能力之比。它与实例数量配比、面积占比并不必然相同。

**模式使用率（Mode Occupancy）**：共享硬件在各运行模式下工作的时间比例，不是额外物理资源。

**硬件特征（Hardware Profile）**：指定设计和运行条件下的功能、时序、成本与活动响应证据。

**工作负载（Workload）**：包含计算形状、数据、依赖、执行频率以及可接受精度条件的任务集合。

**精度可行性（Precision Eligibility）**：某任务在给定格式和计算语义下满足其数值或模型质量要求的条件。

**GEMM 完成延迟（GEMM Completion Latency）**：从任务在声明的起始状态下可被执行，到结果在声明的完成边界可用的时间，包括该边界内的调度、数据移动和计算。
_Avoid_: 与峰值吞吐或纯阵列计算周期混用

**负载功耗（Workload Power）**：指定负载执行窗口内、在明确硬件边界下消耗功率的时间特征，至少区分平均值与峰值口径。
_Avoid_: 与能量或单一满载参考功耗混用

**面积冗余增配（Area-Slack Expansion）**：在已有架构基线的面积余量和其他约束内改变资源配置的设计场景。它不指对已流片芯片增加物理单元。

**Pareto 前沿（Pareto Frontier）**：在相同评价条件下，不能在不恶化任何目标的情况下改善至少一个目标的可行方案集合。
