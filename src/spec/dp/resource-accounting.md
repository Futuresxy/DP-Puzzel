> 功能：定义可统计的功能模块边界；范围：当前 DP 的资源层级、面积/功耗归属、导出与后端报告映射；版本：v1.2.1；修改时间：2026-11-04 20:17:40 +08:00；对应代码：[Chisel](../../chisel/README.md)、[手写 Verilog](../../verilog/README.md)、[DC](../../../hw/dc_syn/README.md)、[功耗](../../../hw/power/README.md)（新版模块及统计流程尚未实现）。

# 功能块边界与面积、功耗统计

状态：用户要求从模块设计阶段保留功能块统计能力。以下定义逻辑功能 ID、职责和报告口径，不创建 RTL/EDA 脚本，不填估算测量值。模块内的算术组合划分不能额外增加八级以外的寄存器。

## 三层架构与功能模块

T1H2Q4E8、T2H4Q8E16 和 H16Q32E64 是架构层级；下表为其内部应可识别的功能块。逻辑 ID 不是已经存在的源码文件名；实施时为 Chisel Module、手写 Verilog module、生成 RTL module 和后端实例建立映射。组合小单元可以复用模块定义，但每个物理实例路径必须唯一。

| 功能 ID | 所属层 / 阶段 | 统计与实现边界 |
| --- | --- | --- |
| operand_unpack | lane / S1 | A/B 格式选择、E/M/S 解码、分类、HiF4 e1、INT8 abs |
| scale_unpack | 基本组 / S1 | A/B scale 到 E8M3 与分类 |
| c_transport | 顶层 / S1–S4 | 原始 C32 和必要控制传递；不复制到每个 lane/组 |
| c_unpack | 顶层 / S5 | FP32 分类/幅值/指数或 INT32 sign/abs |
| mantissa_mul_bank | lane / S2 | 两套 HH/HL/LH/LL 单元；子 ID 区分四个乘法器与部分积重构 |
| exponent_add | lane / S2 | 各活动产品的指数和及选择 |
| lane_exponent_max | lane / S2 | 有限非零候选 MAX |
| group_exponent_max | 基本组 / S2 | 两 lane MAX 合并及回传，无新增寄存延迟 |
| local_delta | lane / S3 | 公共 r 与产品指数的完整差值、饱和控制 |
| local_align_shift | lane / S3 | 四个固定 W-bit 幅值逻辑右移器 |
| e_pair_reduce | lane / S3 | E8→4 的符号求和、HiF4 0/1/2 精确移位 |
| local_sign_convert | lane / S3 | 幅值移位后恢复补码；INT8 符号恢复 |
| lane_sop_tree | lane / S4 | 四路共享 SOP 树，H/T 复用/旁路及自然增长 |
| group_sop_add | 基本组 / S5 | 两 lane 的 SOP 合并 |
| scale_pair_mul | 基本组 / S2 | 两侧 4-bit scale coefficient 的乘积 |
| scale_exponent | 基本组 / S2–S5 | scale 指数和、去 bias、组 top-anchor 标量处理 |
| group_scale_mul | 基本组 / S5 | 紧凑 signed 组和×unsigned scale 系数，NV/HiF4 共享 |
| group_sign_magnitude | 基本组 / S5 | 安全 abs、zero 与组 token 输出 |
| global_anchor_max | 顶层 / S6 | 组与 C 的有效 top-anchor MAX、零/特殊屏蔽 |
| global_delta | 顶层 / S6 | 各源与共同 anchor 的差值与饱和 |
| global_align_shift | 顶层 / S6 | N 个全局幅值移位器，格式间共享 |
| global_sign_convert | 顶层 / S6 | 对齐幅值恢复补码及整数结构落位 |
| final_sop_tree | 顶层 / S7 | N=G+1 输入树，全部增长位保留 |
| fp32_output | 顶层 / S8 | abs/LZD、norm、RNE、pack；保留子功能映射 |
| int32_output | 顶层 / S8 | 结构低零删除、低 32 位输出与选择；不生成浮点逻辑 |
| special_reduce | 各层 / S1–S8 | NaN/Inf/invalid/零符号等摘要与输出选择；必须记录实际归属 |
| request_control | 各层 / S1–S8 | datatype 合法检查、逐级 ctrl/valid/last、局部有效使能 |
| routing_isolation | 各层 / 各级 | 不在上述算术叶内的 mux、operand isolation、扇出 buffer 和旁路 |

乘法器 bank 与 HH/HL/LH/LL、fp32_output 与 LZD/norm/RNE 等是父子统计关系。可提供父级聚合和子级分解两种视图，不能在同一个总计中同时累加两者。组合单元本身不应因为便于统计暗加 pipeline stage；S1–S8 的寄存边界由架构合同控制。

## 资源数量基线

令 G 为基本组数、lanes=2G。每 lane 两套四单元乘法器：总套数=4G、算术乘法单元数=16G；主配置分别 16 套/64 单元。局部四路移位器总数=8G，主配置 32。每组一份 scale-pair 乘法和一份 group-scale 乘法；组 SOP 输出 G 个，全局移位源和最终树扇入为 G+1。输出转换与 C 支路在顶层各共享一份，不按组复制。

这些是当前 RTL 结构预期，不能用门数量或乘法器尺寸乘常数冒充面积。仅在明确输入 mux、输出重构和隔离成本后比较复用收益。综合可能把算术映射为通用门、DSP 或被常量优化，报告保留逻辑资源与物理映射两种视图。

## 寄存器、mux 与时钟的归属

每个有效 cell 只归属一个功能 ID。功能模块若拥有阶段输出寄存器，其 sequential 面积/功耗计入该模块；跨模块的纯传递寄存器分别计入 c_transport、request_control 或具名 transport 子项。模块必须声明寄存器所有权，不能把同一个输出寄存器又加进全局 pipeline-register 总计。

输入 mux/isolation 可作为功能模块子实例，也可归入 routing_isolation；采用哪种方式写入映射，两实现使用同一比较口径。差值器与移位器、scale-pair 与 scale-injection 乘法分别统计，避免用“移位面积”“scale 面积”掩盖其他算子。

时钟网络、reset buffer、跨层优化后无法唯一分配的组合共享 cell 单列为 shared/unattributed，并记录原因。不能为让表格看似完整强行按比例分摊。未接入 CTS 的综合报告不能声称包含实际时钟树成本。

## 生成 RTL 与综合层级

后续 Chisel 使用稳定模块/实例名及显式参数专化；手写 RTL 采用对应逻辑边界。生成 RTL 按既定规则集中于 hw/rtl，文件清单/manifest 记录逻辑 ID→源码→RTL module→实例→参数。复用一个 module 定义的多个实例仍分别统计，不能因只导出一个源文件漏计实例。

综合应输出层级报告及源 RTL 到映射 cell/实例的对应关系。优先保留可报告的功能边界；若自动 ungroup、边界优化、复制或共享破坏映射，记录 affected IDs 和实际映射。无法可靠归属的面积/功耗只能报告到最近可解释的共同父级或 unattributed，不能回填未经证实的细分值。

不为好看的统计无差别添加 dont_touch，也不能把为统计而强制保层次的结果当作完全同设置的优化结果。若需要单独的保层次归因 run 与优化 PPA run，分别标识综合选项、网表、时序和面积影响；两份 netlist 的细分功耗不能混算。当前不指定工具版本相关命令，也不运行后端。

## 面积和功耗报告合同

每个 run 至少关联 spec/config、实现类别、export ID、验证证据、RTL/网表映射、工艺库/PVT、工具版本、时钟/IO 约束和分析命令。每个功能条目包含：logical_id、instance_path、parent_id、stage、参数/资源计数、是否被展开/合并、combinational/sequential area、单位、数据来源和归属状态。

层级报告明确 `inclusive`（包含子模块）与 `exclusive/self`（仅本级 cell）面积。计算总面积采用互不相交的叶 cell 集合或 self 值求和；总和与顶层值核对，并单列 buffer/shared/unattributed 差额。源代码行数和源码模块数不能作为面积占比。

功耗条目分别记录 internal、switching、leakage、total，以及 VCD/SAIF 来源、时间窗口、时钟/电压、标注覆盖率、未标注网络的默认活动与毛刺/寄生假设。父子 inclusive 功耗不能重复相加。保存源映射使每个功能块能回溯其活动；一次单模块孤立综合/功耗不能替代顶层环境中的实际值。

共享单元的**物理面积只统计一次**；TF32、FP16、Q、E、INT8 的动态功耗可在各自负载窗口分别测量，不能按 datatype 把物理面积复制成多份。混格式请求现已合法，需另外测量格式切换、bubble、idle 与不同活动掩码；不能用单格式稳定活动推断混格式功耗。拆分流水级不等于拆分时钟域。

未来报告应同时提供按架构层级、功能类别、阶段和运行格式/负载的视图；它们是同一数据集的不同聚合，不是可相加的四份成本。未知或未测值保持 unknown/null。当前未产生任何 DC/功耗结果。

## v1.2.1：规格化候选的统计项

若后续采用 [组实际指数检测](group-normalization-options.md)，另记录 group_leading_detect、group_anchor_adjust、c_subnormal_detect 以及 S6 方向 mux/合并移位的资源。它们目前仅是候选 ID，不表示已实例化。分别比较完整规格化的左移器、合并方案的方向控制与粗粒度版增加的窗口/寄存位；S3 的固定共享移位器不因 S6 方案更换而复制。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 新建统计合同 | 按乘法/指数/MAX/移位/SOP/scale/解包/输出与控制拆功能 ID；定义寄存/mux 归属和避免面积/功耗重复计数的后端映射。 | 用户模块化统计要求 |
| v1.2.1 | 2026-11-04 20:17:40 +08:00 | 讨论/说明补充 | 记录组实际指数候选及对应数值、特殊值或资源边界；不改变 v1.2 主路径。 | 用户 LZD/指数/特殊值讨论；[总时间线](../CHANGELOG.md) |
