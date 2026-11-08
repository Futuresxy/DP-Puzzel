# DAC 2027 工程开发约定

## 当前优先约定：新版 DP / Cube（2026-11-04）

用户已明确旧 DP 设计过时，由用户重新定义整体架构 spec。新设计统一放在根目录 `src/spec/`、`src/cmodel/`、`src/chisel/`、`src/verilog/`，共用测试放在根目录 `test/`。先逐项完善并确认整体 spec，再编写 CModel，之后开发 Chisel 和独立手写可综合 Verilog；用户已授权实现单 DP 手写 Verilog，SystemVerilog 已冻结为当前 T8H16Q32E64 的历史参考，不再同步维护；CModel 与单 DP RTL 已建立共用验证，Chisel、阵列尚未实施，单 DP 已完成 N12 DC 综合。首批要求已写入 [新 spec 索引](src/spec/README.md)：TensorCore → DP-Group → DP，16×4 阵列由四个竖直 4×4 广播组组成；组内无脉动。具体格式、精度、K、≤8级流水、1.41 GHz 和功耗优先约束以新版 spec 为准，未决口径不得从旧设计补齐。

E 专用前端已按所选 E64 方案实现 CModel（S2 pair、S3 lane 树、S4 组和/abs、S5 scale），与多精度前端共用 S5 Token/C 解包及 S6–S8。配置为 src/configs/dp/e64.json；E 纯 Verilog 顶层为 src/verilog/top/dp_top_e.v，专用 dp_lane_e/dp_group_e 使用 files_e.f，--frontend e 完成独立 Verilator/lint/断点/协议验证。混合组 v1.7 已实现 QE CModel/Verilog 和三个固定配比顶层，验证入口为 test/run_mixed_verilog.py，阶段记录见 test/results/mixed-cmodel-v1.7.md、test/results/mixed-rtl-v1.7.md；三个混合顶层和当前多精度基线已完成 N12 TT/1GHz、门控开启的综合，保持 L8/II=1，setup/hold/VT/电气规则均通过，比较见 hw/dc_syn/records/mixed_n12_1000mhz_20261108.md；本轮用户明确授权 DC 综合并要求此次验证、综合及比较基线长期保留，精简证据见 test/results/e64-v1.5.8.md 与 hw/dc_syn/records/e64_n12_comparison_20261105.md，不把仿真通过作为时序/功耗证据。

历史 PE 实现及其规格、配置和验证从 Git 历史查阅。新版设计由 `src/spec/` 的共用合同和源码映射定义。

当前工作目录使用根 `src/` 开发、`test/` 验证、`hw/` 做综合与功耗。分析前将设计冻结到 `hw/rtl/<export-id>/`，在 manifest 记录顶层、时钟、复位和来源。DC 流程自身的测试位于 `hw/dc_syn/tests/`。

新版 spec 文档维护遵从 [版本与修订规则](src/spec/document-control.md)：每份 `src/spec/**/*.md` 第一行必须写功能、范围、固定版本、修改时间及时区、对应代码文件（未建时明确标注并指向现有入口）。当前架构 v1.7、实现映射 v1.7.1；同架构修订追加 `.x`，架构合同修改升新 vM.N 并记录原因与影响。按用户最新要求，正文只展示当前有效合同，清除过时草案与重复历史；仅相邻两个主要版本的核心变更保留简短删除线对照，非核心小修直接更新。完整历史由 Git 保存，当前索引与两版摘要见 [版本记录](src/spec/CHANGELOG.md)。版本编号不代表待决规格已批准或实现已验证。

用户于 2026-11-05 另行授权在本机 EDA 环境执行单 DP 的 N12 DC 综合及 1.41GHz 时序分析。此授权覆盖验证门禁与综合基础设施接入，不扩展计算阵列；后续按用户授权和真实证据运行对应 EDA 流程。

用户于 2026-11-05 明确：`src/verilog/systemverilog/` 仅保留 T8H16Q32E64、K16/28/40、L8/II=1 的历史版本，后续新特性、数值/流水优化和 E 类专用 DP 不再同步到 SV。当前维护 CModel 与纯 Verilog；默认 RTL 回归只运行 Verilog，显式 SV 重放为历史参考检查，不作为新版本门禁。Chisel 仍按原计划待实施；测试台使用 Verilog/SystemVerilog 语言不改变 DUT 的维护范围。冻结来源见 [SV 说明](src/verilog/systemverilog/README.md)。


用户于2026-11-08要求DC结果区只保留六种现用架构各自最新有效结果，覆盖此前对已删除旧run的保留约定。当前索引为 hw/dc_syn/records/latest_six_dp.{md,json}；修复来源放在最终run的provenance/repair_sources/并校验hash。旧精简报告从Git历史读取，清理回执在hw/dc_syn/maintenance/。后续功耗显式选择catalog中的最终网表；尚未完成门级等价/SAIF/活动审计，不能标注为功耗已就绪。

## 历史设计约定与通用工程规则

本文件适用于整个仓库。目标是构建面向 AI 芯片张量计算的多精度算力配比 DSE 系统，对 BF16/FP16、MXFP8/6、MXFP4/NVFP4/HiF4 等设计选择的面积、功耗和负载延迟进行成本收益权衡。

**阵列扩展当前仅获授权调研和方案讨论，用户审核确定方案前不写阵列代码。** 已确认采用 2×2 group 组内广播、组间脉动；M8N32 是逻辑指令输出块，物理阵列参数化；FP4 目标 K64/96/128/192/256，FP8 目标 K32/64/96/128。控制、L0 和 layout 候选见 [讨论稿](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/array-design-discussion.md)，其中建议不等于已批准的实现合同。

阵列调研须覆盖逻辑指令以下的物理 tile 切分、preload/compute/drain、本地 accumulator 与累加 RAW。区分 L0 层输出驻留和 PE/group 内 OS；文献已实现机制、逆向推断与本项目建议分别标记。当前候选与证据见 [OS 调度调研](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/os-array-scheduling-research.md)。

当前讨论方向为 `K_inst = K_native(mode, config)`：指令内只调度 M/N 输出子块；更长 GEMM 的 K 由软件组织多条原生指令，K-PE 内部空间规约保留。不得继续将 E64 分三轮执行 K192 作为单条原生指令的默认方案，也不得由固定 PTX K 推断 NVIDIA 内部没有时分计算。跨指令 C/D 依赖及驻留合同仍需审核；本方向不构成阵列代码实施授权。

Ascend 的16³基本计算粒度与可变M/N/K的MMAD指令另见 [对照调研](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/ascend-cube-scheduling-research.md)。不能把其FP16基本K16误当作指令K上限；原生K指令和可变K矩阵指令属于不同候选边界，等待用户讨论确定。

厂商指令边界应从官方仓库的固定版本源码出发，追到编译器 intrinsic 和可获得的 IR/汇编/机器码；不能用一次 API 调用代替一条机器指令。参数可编码范围、L0/布局约束与真实芯片验收分别记录。官方 Ascend C v9.1.0 的编译核验见 [ISA 分析](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/spec/array_ref/ascend-official-mmad-isa-analysis.md)。

先阅读 `README.md`、`CONTEXT.md` 和 `docs/architecture.md`。`hw` 只负责单阵列/单核心；`ratio_dse` 负责多核心、多阵列芯片级建模。未定案事项记录在 `docs/roadmap.md`，不能用 INT4/INT8 示例代替目标浮点格式。

## 1. 目录与职责

- `src/spec/`：接口、数值语义、参数约束、数据流、周期和验收标准。
- `src/cmodel/`、`src/chisel/`、`src/verilog/`：模型及设计源码、可复现参数配置。
- `test/`：参考模型、测试数据、功能验证与回执。
- `hw/rtl/`：用于综合和功耗分析的唯一 RTL 快照位置。
- `hw/dc_syn/`：挂载 EDA 环境内的 Design Compiler 综合、面积与时序流程。
- `hw/power/`：活动信息、功耗分析脚本和报告。
- `hw/characterization/`：经过验证、可追溯的硬件特征数据，供 DSE 引用。
- `ratio_dse/`：芯片共享 HBM、多核心 L1/L0/阵列、负载映射与调度、芯片面积/功耗/延迟建模和配比扫描。
- `scripts/`：构建、导出、验证和环境检查入口。
- `paper/`：DAC 2027 论文正文、模板、图表、参考文献与投稿资料；论断和数字必须能回溯到验证结果。
- `.skill/<name>/SKILL.md`：所有本项目新增/维护的技能统一存放处，包括 DC 综合、功耗分析等；不得分散到其他目录。
- `.codex/`、`.agents/` 等已有开发配置：保留，不覆盖用户设置，不作为清理目标。
- `ref_work/`：本地参考项目和工作，整体不提交 Git；可阅读以参考、优化或评估依赖。
- `dependencies/`：跟踪第三方来源、固定版本和获取说明；`.deps/`：实际下载/克隆的第三方源码，整体不提交 Git。

## 2. Chisel 风格与命名

1. 简约、直观、可审查；优先清晰的硬件结构，避免为少量逻辑引入复杂继承、泛型框架和隐式转换。
2. Scala 使用两空格缩进、UTF-8、LF；Module/Bundle/参数类型用 `UpperCamelCase`（用户指定的SubPE_H、PEGroup_HQE、PE_E等族名例外），参数字段与 Scala 辅助方法用 `lowerCamelCase`，package 小写。
3. 硬件端口、寄存器、连线用 `lower_snake_case`。端口用 `in_`、`out_` 前缀，寄存器用 `_q`，组合下一状态用 `_d`，使能用 `_en`，低有效信号用 `_n`。时钟/复位保留 Chisel 默认 `clock`/`reset`；异步复位必须由 spec 明确要求。
4. 实例名表达功能，例如 `dot_product`、`input_buffer`；避免 `tmp1`、`data2` 等无语义名称。顶层 `desiredName` 稳定，与导出映射一致。
5. 使用不可变 `case class` 集中参数化，使用 `require` 检查合法范围、整除关系和位宽约束。不得把测试配置写死在设计里，不增加尚无需求的参数。
6. 位宽、signed/unsigned、扩展、截断、舍入、饱和和溢出行为必须显式定义。乘法/累加保留所需精度，禁止依赖隐式截断获得“正确结果”。单元素和非二次幂参数必须有明确行为。
7. 每个 Module 注释说明功能、接口协议、延迟、吞吐、复位和数值语义；关键逻辑注释说明设计理由、位宽推导或时序取舍，不逐句翻译代码。
8. 组合逻辑完整赋值，避免锁存器、组合环和多驱动；禁止以 `DontCare` 掩盖未实现功能。提交的模块必须具备完整可运行实现，未实现方案只放在 spec。
9. 修改 Chisel 前读取 [.skill/chisel-design/SKILL.md](.skill/chisel-design/SKILL.md)。源码与对应 `src/spec/` 合同在同一批次更新。规格解释架构、位宽、共享资源、接口、周期和验收。

## 2a. 手写 RTL 风格与流水寄存器

设计、修改或审查维护中的 Verilog 前读取 [.skill/dp-rtl-code-style/SKILL.md](.skill/dp-rtl-code-style/SKILL.md)。用户于 2026-11-06 确认：每条声明只定义一个变量，端口逐行重复完整方向/类型/位宽，`parameter/localparam` 等同样拆开；这取代之前合并同类变量的排版约定。时钟保留 `clock`，复位采用**同步低有效 `rst_n`**；所有流水寄存器统一实例化参数化 DFF 模块，区分带同步复位的控制寄存器和无复位、带使能的数据寄存器。valid 每拍推进以传递气泡，payload 仅在有效时更新，不增加流水级数。

参考 SN 风格适配后的项目规范采用模块 `dp_`、宏 `DP_`、DFF 实例 `ff_<源阶段>_<目标阶段>_<功能>` 命名；字段布局集中定义，内部寄存打包紧邻解包。DFF 生产实现位于 src/verilog/common/；skill assets 保留参考模板，不能同时加入生产清单。 用户进一步要求尽量保留 SN 完整规范：主体包含详细规则、示例、六种 DFF/组合单元说明及逐项自检；新功能组合使用 assign（FSM 次态例外）、条件先归约后按位组合、动态选择显式组织 MUX。DFF 统一紧凑两行：模块类型/参数一行，实例名及全部端口一行（豁免 100 列）；连续 DFF 区块局部关闭 Verible 排版保护，声明仍每行一个。DFF 紧随本级计算、置于下一级使用之前，旁带就地同行；不得将各级 DFF 统一集中到文件末尾。

最新流水变量约定先在 dp_lane.v 落实：寄存值用 rN_<功能>（r1_valid、r2_product_magnitudes），组合候选用功能名_d；同组赋值按等号对齐，完整函数/分支不机械拆行，参数及变量首次声明前说明作用。其他模块按任务范围逐步迁移，冻结 SV 不改。

命名相关设计、修改和审查同时读取 [.skill/dp-naming-convention/SKILL.md](.skill/dp-naming-convention/SKILL.md)。文件/module/实例/变量需表达实际功能，禁止局部数值使用裸 e/f/a 等不明缩写；指数域、指数值、域宽、定点小数位数分别命名。父层互联使用 driver_receiver_function，复用模块端口保持 in_/out_，本地变量不重复端点；数学操作数 in_a/in_b/in_c、E 前端后缀 _e 和库端口 in_d/out_q 是已定义例外。循环索引使用 lane_index/element_index 等角色名。现用 CModel/Verilog 已按任务迁移命名，稳定的数学操作数及 JSON trace 字段保留其已定义语义。

v1.6 已迁移现用 Verilog 为同步低有效 `rst_n` 和显式 DFF，并同步接口 spec、TB、导出及 EDA 阶段识别；当前验收见 test/results/dp-style-v1.6.md，不将旧快照/PPA 视为新实现验收。冻结 SystemVerilog 不迁移，Chisel 默认端口约定保持原范围。

## 3. 面积、时序与功耗

- 工作负载功耗的方案和实测流程见 [power-analysis](.skill/power-analysis/SKILL.md)。实际测量遵循当前任务的授权范围。
- 选择满足精度与吞吐的最小位宽；控制计数器不得习惯性使用 32/64 位。
- 点积优先使用平衡加法树，避免长串行加法链；流水位置由目标周期和实测时序确定，并同步修改延迟 spec 和测试。
- 显式控制资源复制、MUX 深度和广播扇出；仅在吞吐允许且数据支持时复用运算器。
- 数据无效时用寄存器使能保持数据，减少切换；不能只因输出无效就假定组合乘法器没有活动。必要时评估 operand isolation 的面积/时序代价。
- 默认不复位无需初始化的数据通路寄存器，以有效位屏蔽未定义数据；控制/有效位必须正确复位。禁止随意使用生成时钟，时钟门控必须走经过验证的工艺单元流程。
- PPA 取舍必须有相同工艺库、PVT、约束、负载和工具版本下的证据。综合面积不是布局布线后面积；vectorless 功耗不是 workload 驱动功耗；时序未达标不能宣称达到目标频率。

## 4. RTL 单一来源与导出

1. 将待分析设计从 `src/` 冻结或导出到独立的 `hw/rtl/<export-id>/`。DP 手写实现使用源内容指纹形成 `DP_verilog_<fingerprint>`，导出流程记录实际顶层、时钟、复位和参数。
2. 每个目录必须有 `README.md`、`manifest.json`、`files.f`、`src/`。README 每次记录时间、原因、源码指纹/Git commit（可用时）、参数、工具版本、模块映射、命令和验证状态。不能静默覆盖旧导出。
3. 使用编译工具的 split Verilog 能力导出；每个生成 module 独立保存为同名 `.sv`，记录对应的 Chisel 类/文件和参数特化。共享 module 定义只保存一次；不得随意 flatten/inline 破坏映射。工具辅助 module、blackbox、头文件也必须进入清单并说明来源。新增层级时同时更新映射和检查。
4. `files.f` 使用相对导出目录的路径；仿真、DC、功耗流程用显式 export ID 解析该清单并核对 SHA-256。禁止复制到各自目录、手工修补 `.sv`、用模糊 glob 或“最新文件”作为分析输入。
5. 导出状态为 `generated`，对该份 RTL 仿真通过后才能成为 `passed`。仅 Scala 编译/Chisel elaboration 成功不等于 RTL 验证通过。RTL 或验证代码发生修改必须重新验证；失败或文件指纹不一致立即阻止 PPA。
6. PPA 入口必须调用统一的 RTL 验证门禁，校验导出清单、RTL hash 和该份 RTL 的通过证据；不能手改 manifest 伪造通过。门禁接口与实现须在接入 EDA 前完成。
7. 综合 netlist、DDC、SDF 是衍生产物，放在对应分析 run 内并记录源 export ID。功耗使用经验证 RTL，或经一致性验证、具有完整来源的综合 netlist；两者不混用。

## 5. 测试与分析顺序

硬件证据顺序为：spec → 参数配置 → Chisel → RTL 导出 → RTL 回归 → DC/时序 → 真实负载功耗 → characterization → 校准后的 DSE。允许 DSE 提前基于明确标注的解析假设开发，但不能冒充硬件实测或校准结果。

- 测试覆盖合法最小参数、常用参数、非二次幂尺寸、非法参数、数值边界、符号、随机输入、连续有效、气泡和复位；支持反压的模块还必须验证停顿和恢复。
- 固定并记录随机种子，以独立数值参考模型比对结果；同时检查延迟、吞吐和有效信号。无效输出不得作为数值结果。
- 最终通过依据必须是 Verilog/SystemVerilog testbench 对导出 RTL 的数值精度和周期协议验证。Chisel 小模块测试只能辅助。各格式明确 bit-exact 或有依据的误差界限，不以宽松阈值掩盖舍入/缩放错误。
- 参数变体分别导出、分别测试；一个配置通过不代表所有配置通过。
- DC 记录 PDK/library 标识、PVT、时钟/IO 约束、面积单位、critical path、slack 和未约束路径。缺少工艺库或许可证时明确报告未执行，禁止填写估算值冒充测量。
- 功耗记录电压、频率、温度、活动来源、仿真窗口、层次路径、annotation coverage、静态/动态功耗和工具版本。与 RTL 不匹配的 VCD/SAIF 不得使用。
- 每个运行记录配置、版本、命令、摘要和输入指纹，记录寿命遵从第 7 节。重大版本、里程碑、论文与 DSE 的长期证据在与用户确认后标记保留。
- `dc_syn` 和 `power` 必须在当前机器挂载的 EDA 环境中执行；按用户授权与工具环境运行，记录挂载路径与工具/库版本，私有路径和许可证配置不提交。

## 6. ratio_dse 约定

- 分离格式、硬件实现、负载、映射、芯片拓扑、存储、调度和搜索。模型面向多个 SM/AICore 类核心组成的 AI 芯片；具体厂商实现只作参照。未建模的 SIMT、L2、互连等必须注明固定开销、近似或排除边界。
- 目标格式为 BF16、FP16、MXFP8、MXFP6、MXFP4、NVFP4、HiF4；不同编码、缩放粒度、累加精度、舍入与转换成本分别建模。HiF4 的具体规范版本仍待确认，不能臆造位布局。
- 同时报告实例数配比、峰值 MAC/cycle 配比和可用时的面积配比；MAC=1 次乘加，若报告 OP 则明确按 2 OP/MAC 计数。不得混淆面积占比和算力占比。
- 周期模型显式考虑 tiling、阵列 fill/drain、K 方向 dot 长度、边界利用率、数据传输、buffer 容量和复用。重叠传输必须有调度/双缓冲依据；不能随意取 max 隐藏开销。
- characterization 必须带 export ID、验证证据、工具/工艺和数据来源。未校准模型输出标记 `analytical_uncalibrated`；未知面积/功耗用 null，不以零代替。
- 区分物理实例分配与共享多模式单元的模式使用率；共享单元的不同模式峰值不能同时加总。阵列 profile 与已包含阵列的 core profile 不能叠加重复计算。
- 输出 `area`、真实 workload 下的 `power`、`gemm_compute_latency` 的多目标权衡与 Pareto 前沿；没有用户权重时不归并为单一分数。能耗可作派生指标，不能替代功耗。
- 扫描明确面积冗余增配或下一代芯片设计场景、预算、工艺/PVT、频率、HBM、工作负载与精度可行性。新增阵列属于设计变更，不是对已流片芯片的运行时改装。
- GEMM latency 区分纯阵列服务时间与包含映射、存储、调度、必要格式转换的完成延迟；芯片多核心场景不得直接拿单核周期数除以核心数。

## 7. 清理与版本管理

- CModel、RTL 验证、DC、功耗各自滚动保留最近两次已结束且无引用的普通运行。读完结果后用 [运行保留入口](scripts/README.md#运行产物保留) 预览并清理超出的最旧普通运行。失败且仍在调查的最小复现与日志保留到调查结束。
- 重大版本与重要节点先向用户确认具体 run ID 和理由，再标记长期保留。现用 RTL 回执、仍被报告或下游运行引用的输入及无法确认状态的旧目录不参与滚动删除。确认的重要运行也不占普通运行的两个名额。
- 清理只限本项目拥有的生成目录。禁止 `git clean -xfd` 等无差别清理，禁止触及开发配置、凭据、用户文件、论文引用结果和正在运行的实验。
- 历史成功 RTL 若无测试/PPA/DSE/论文引用且已被替代，可在确认引用关系后清理；manifest/README 保留失效记录。不得删除仍被下游引用的输入。
- 远程仓库为 `git@github.com:Futuresxy/DP-Puzzel.git`。开始工作先检查 status、当前分支与远程历史，保护用户未提交变更，不 force-push。
- 小功能、修复和文档更新直接在本地 `feat/dp-verilog-v14` 开发并提交。只有需要独立并行推进的大任务才建立工作分支，经审查和必要检查后通过 PR 合入 `main`。
- 创建或删除本地和远端分支前须获得用户同意。临时工作分支合入目标分支后，核对提交已包含在目标历史中，经用户同意清理本地及远端分支。保留仍在开发的分支。
- 小改动在完成检查后保留本地提交。并行工作分支应及时提交和推送，未完成的工作可用 draft PR 记录进度。重大架构变更、关键实验和特征数据在形成可复现批次后及时同步。
- 每个批次先检查，再更新文档和记录，审查 diff 与待提交文件大小，然后显式 `git add` 并提交。并行任务推送分支后创建或更新 PR，说明问题、变化、验证、数据来源和限制。
- 合入 `main` 前须解决冲突并通过必要检查。
- 不提交缓存、大型仿真产物、PDK、商业库、密钥或机器私有路径。源码、测试、配置、文档及小型结果摘要进入 Git；大产物使用有校验和的归档位置。
- 单文件超过 5 MiB 默认拒绝加入版本控制；确有必要时先选择外部归档/LFS 策略并记录原因。关键数据更新提交精简摘要、schema、配置和归档 hash/位置，不提交原始巨大数据。`.gitignore` 无法移除已经被跟踪的文件，检查 staged 文件仍是必需步骤。
- 网络、权限、凭据或冲突阻止同步时，明确记录未完成的 commit/push；不能宣称已远程保存，也不能绕过受保护的 `.git`。
- 保留 `.codex`、`.skill` 等开发支持目录。项目共享设置可审查后提交；令牌、会话、机器设置不进入仓库。

## 8. 参考工作与第三方依赖

- 所有新技能只放 `.skill/<name>/SKILL.md`，脚本/参考文件放该技能子目录；优先复用 `scripts/` 中的公共入口。
- `ref_work/` 可用于阅读、对比和优化；禁止 `git add -f` 将其加入仓库，禁止清理时删除。引用参考结论须保留来源，不能把参考项目的结果冒充本项目测量。
- CACTI 等外部建模/仿真项目作为依赖接入：在 `dependencies/` 的版本清单中记录上游 URL、固定 commit、许可证说明和用途，在需要时 clone 到 `.deps/`。清单与拉取工具在实施阶段建立。
- 项目只跟踪 adapter/wrapper、输入配置、必要补丁和版本信息；不得把第三方整个源码树复制进 `hw/`、`ratio_dse/` 或仓库其他被跟踪目录。
- 版本必须固定到可复现 commit；不能以浮动 main/master 作为正式实验依赖。版本未确定时明确保持未启用状态，不自动选择版本或伪造模型数据。
- 第三方构建产物保留在依赖目录或被忽略的 run 目录；记录调用命令、版本、输入 hash 和单位，避免把第三方访问时间/能耗直接误作完整芯片指标。

## 9. 论文与写作技能

- `paper/template/` 保存有来源/版本/许可证的 LaTeX 模板，`paper/main.tex` 为论文入口，章节、图、表、参考文献分目录维护。当前只准备空白写作结构，不生成研究结果或贡献声明。
- 论文写作/润色时按任务读取 `.skill/academic-humanizer/SKILL.md`；这是用户指定安装的项目技能，保持数据、引用、符号与结论强度不被润色改变。其上游版本见同目录 INSTALLATION.md。
- 图表必须关联实验 run、配置、profile 和生成数据；不能把未校准假设写成实测结论。参考文献先核验真实来源，禁止编造引用。
- DAC 规则按 `paper/submission/requirements.md` 及官方最新页面核对；维护匿名性、页数与适用 AI 使用披露。仅语言编辑与生成研究内容的记录分开，不把 skill 当作免除披露的手段。
- 编译产物、大型原文 PDF/数据不提交；必要的图表 PDF、BibTeX、模板文件与图源可提交，不能用全局 `*.pdf` 忽略误伤图表。
