> 功能：定义 DP CModel、模块映射及共用测试接口；范围：分组共享 DP 的整数数值、逐周期执行、精度参考及证据边界；版本：v1.7.4；修改时间：2026-11-08 09:03:06 +0800；对应代码：[模型 API](../../../cmodel/include/dp/model.hpp)、[参数](../../../cmodel/include/dp/config.hpp)、[执行器](../../../cmodel/lib/model.cpp)、[测试入口](../../../../test/run_cmodel.py)；Chisel 尚未实现；手写 RTL 映射见 [实现合同](verilog.md)。

# DP CModel 合同

模型实现多精度分组共享前端和 E 专用前端，共用 S5 token 完成/C 路径及 S6–S8。默认 `multi` 为 T8H16Q32E64，`e` 为 E64，均为 L8、II=1。E 前端仅支持 MXFP4/NVFP4/HiF4，C/D 为 FP32；数学参考和请求接口复用。QE 和 E96/E128/Q64E128 混合组组合已实现，见混合顶层合同与独立验证；阵列尚未实施。各 RTL 及 DC 均有对应快照证据。模型不以宿主 float/double 代替有限位宽运算。

## 1. 实现与模块映射

| 文件（相对 src/cmodel/） | 责任 / 硬件对应 |
| --- | --- |
| include/dp/config.hpp、lib/config.cpp | 集中格式常量、配置及自然位宽/树深派生；合法类型和输入约束 |
| include/dp/model.hpp、lib/detail.hpp | 请求、结果、flags、逐级状态与 group token |
| lib/unpack.cpp | S1 A/B/scale 解包为 E/M/S 与分类；S5 C 解包辅助 |
| lib/lane.cpp | T1H2Q4E8：S2 乘法重构/指数和/MAX，S3 幅值 RTZ/E pair，S4 lane 树 |
| lib/group.cpp | 多精度 T2H4Q8E16 的 S5 合并/abs/scale |
| lib/lane/lane_e.cpp | E8：S2 无符号 4×4 与 signed10 pair，S3 四项树到 signed12 |
| lib/group/group_e.cpp | E16：S4 融合 e2/固定补零、两 lane 合并/abs，S5 scale 与兼容 Token |
| lib/top/backend.cpp | 共用 S5 LZD/C 解包、可选独立 LZD 级、S6 对齐、S7 树、S8 RNE/INT32 |
| lib/arithmetic.cpp | 整数宽度断言、平衡加法树、RTZ、RNE、特殊值摘要 |
| lib/model.cpp | 事务 evaluate 与逐级 Pipeline；二者使用同一 stage 函数 |
| lib/json_io.cpp、main.cpp | JSONL 协议、固定宽度 hex/枚举检查、CLI |

C++ 使用 Boost cpp_int 保存精确整数，**在规定截断点显式 RTZ，在其他出口检查位宽**；大整数不代表硬件具有无限宽窗口。每个 occupied stage 在 step 中只前进一级，没有提前算完再延迟输出。软件保留旧字段/trace 是诊断便利，不作为 RTL 寄存器数或 PPA 估算。

## 2. 参数合同

四项数值参数：k_fp16（4/8/16），local_shift_mag_width（默认 28、至少 27），global_signed_align_width（默认 40），post_scale_norm_extra_stage（0/1，默认 0）。另有静态 `frontend`：`multi`（默认）或 `e`，不作为请求信号。配置是显式 JSON 对象；未知键、非法类型、负数、小数、溢出值及非法组合报错，不通过环境变量隐式修改数值。E64 的实际配置见 [e64.json](../../../configs/dp/e64.json)；兼容 k_fp16 只决定 G=K/4，不表示 E 前端支持 FP16。

多精度前端派生量：G=K/4，leaf=local+1，lane=leaf+ceil_log2(4)，group=lane+ceil_log2(2)。两种前端的公共 S5 group_mag=local+3、global_mag=global−1、sum=global+ceil_log2(G+1)。E 的内部 pair/lane/group 为 10/12/15 位，14 位组幅值不随 LOCAL_W 增大；E 配置回显单列 pair_bits、lane_bits、group_internal_mag_bits 及兼容 group_mag_bits。要求 global_mag≥max(group_mag,32)，所有静态 pad 非负。当前窗口扫描是建模探索，不把允许构建的每个窗口宣称满足用户 35/37 位精度目标；默认及已测配置单独记录。

格式常量、E guard、scale 窗口和每模式 F 见 [数值布局](../common/numeric-layout.md)、[逐级出口](../common/stage-formats.md)。S2 raw 元素指数不去 bias；S5 形成无偏原 anchor。C 同样在 S5 去 FP32 bias。S6 用 signed 真实指数 MAX 和完整 unsigned d；S8 仅为最终 FP32 编码加一次 127。

S5 先分离符号和幅值。NVFP4/HiF4 共用 **14×8 无符号 scale 乘法**，22 位乘积补零后用于 LZD 计数。S6 net=z−d 一次双向移位后恢复补码。详见 [scale 合同](../group/scale.md)。模型逐笔携带控制，last 只透传。

## 3. 逐级数值与周期 API

`evaluate(config, request, trace)` 返回一笔完整结果。`Pipeline(config, trace).step(request, a_valid, b_valid, c_valid, reset_requested)` 返回本时钟沿前可见输出，再推进各级。三路都有效、类型元组合法且非 reset 时原子接收；气泡和非法类型不阻塞在途结果。`reset_requested=true` 是软件复位事件，映射为 RTL `rst_n=0`；JSONL 仍保留 `reset` 布尔字段。该事件丢弃全部在途请求。

沿 n 接收，S1 在 n 更新，S8 在 n+7 更新，step(n+8) 返回结果，因此报告 L8。每拍均可接收，输出无 ready。可选 L9 的 S5 仍完成 abs/scale/原 anchor/C 解包，新增一级只做 LZD，后三级整体顺延；默认测试数据和期望采用 L8，L9 仅作数值/寄存边界探索，未因模型存在而自动选择 RTL L9。

`id` 为验证器侧关联编号，不新增 DUT tag 端口。`protocol_error` 为驱动诊断，不新增 DUT 错误端口。all_valid 下非法类型拒绝握手；超宽数据、TF32/FP6 非零填充、错误 scale 广播/负 NV scale 等源违反 payload 合同会抛异常，且在周期状态更新前检查。partial-valid 时不解读无效请求内容。

trace 的每个 cutpoint 有 stage、operation、data。覆盖 S1 每元素及 packed E/M/S、S2 magnitude/exponent/F/r、S3 signed leaves/移位差、S4 lane SOP/F、S5 raw group/C token 与共享 scale 乘法操作数、S6 E_max/z/d/net/对齐值、S7 总和/F、S8 输出。token 保留 sign、m、width、F、anchor_raw、z、派生 e 与 zero/special。整数和特殊值未使用的浮点控制是安全占位，不作为数值指数。

E 的 S2/S3/S4 观察点分别为 `e_multiply_and_pairs`、`e_lane_sop_tree`、`e_group_sum_and_abs`；S5 起共用原 token/trace 接口。HiF4 在 S4 消耗 p=e2_a+e2_b，输出 F 与原多精度路径不同；按 [E group 坐标合同](../group/dp_group_E.md#4-与原多精度-group-对齐的输出-layout) 检查 m/A/z 映射，S6 对齐叶子、S7、S8 逐位一致。S3 可提前准备 anchor 是硬件时序安排，当前 CModel 在 S2 保存 scale 指数和、S5 计算 anchor，不额外增加寄存级。

模型可检查范围/等式和周期边界；逻辑阶段不能证明实际组合延迟符合 1.41GHz。S2 MAX 回传、S5 scale→LZD、S6 MAX→双向移位、S8 norm/RNE 都仍须 RTL/工艺时序验证。

## 4. 特殊值、舍入和诊断

已确认 canonical qNaN=0x7fc00000、RNE、渐进下溢、舍入后 tininess。精确抵消为 +0，仅所有零项为负时保留 −0，最终微小负数舍入零保留负号。sNaN、0×Inf、异号 Inf 求和的 invalid 不因另一项 NaN 被屏蔽。见 [特殊值合同](../common/special-values.md)。

结果 flags 仅供验证：invalid、overflow、underflow、inexact 为已定义有限路径的异常诊断；local_truncated/global_truncated 分别记录两次 RTZ 丢位。S8 inexact 不等价于理想点积相对输出的全程 inexact；不把早先丢位重新注入最终舍入。INT32 内部精确求和，输出模 2^32，另记 integer_overflow。

## 5. 同一份激励与两类参考

规范化输入是 [DP_INPUTS_V1](../../../../test/data/README.md)，位布局对应 [DP 顶层接口](../dptop/interface.md)。九格式来自旧 correct_961，只导入新版要求的 K，不导入旧阈值/通过结论。原文件只读，SHA256/原始五段来源记录在每份 manifest。TF32 K8/INT8 K32 固定种子构造后使用同一 layout。

1. C++ 对独立 Python Fraction **有限窗口参考**逐位比较：后者在实数 dyadic 坐标按局部/全局网格 RTZ，不复用 C++ 的容器落位、部分积重构或 z−d 代码。
2. 对无限精度 Fraction 点积加 C 后一次 FP32 RNE 计算 ULP/绝对误差；不要求已截断架构全部逐位相等。对每个实际丢位项，累加一次局部量化单位乘 scale 绝对值，加每个全局丢位项的量化单位，再加最终半 ULP，得到每例可计算的绝对误差上界。数值接近零时 ULP 可放大，不用固定宽松 ULP 门槛掩盖误差。
3. TF32 另记录 FP64 math.fsum 参考。它是近似；精确边界/负零由 Fraction 独立复核并记录差异 ID。INT8 必须与无界整数参考（含 C 和回绕）完全一致。

`expected.jsonl` 来自已通过独立检查的 CModel，同时保存理想数学结果。未来 Chisel RTL 与手写 Verilog 必须逐位对齐其中 d/type/last，并按相同周期事件检查 valid；不能用数学误差阈值放宽 RTL 对 CModel 的一致性。

## 6. 验证和剩余边界

执行说明见 [CModel](../../../cmodel/README.md)；首批结果见 [报告](../../../../test/results/cmodel-v1.4.md)。单测覆盖 K4/K8/K16、2/3/5 项树、三组窗口、L8/L9、相邻换型、reset、气泡、无效类型、输入填充/广播、small-code 与 scale 编码、特殊值/RNE 边界、INT 极值及回绕。只对已列组合作覆盖声明；不是所有 A/B 编码笛卡尔积穷举。

CModel、现用 Verilog 及未来 Chisel 使用共同数学合同；SV 历史目录按冻结版本解释。 C++ 文件不等于最终 RTL module 一一结构实例化；operand isolation、时钟门控、mux 门级共享和面积归属仍须实现和综合证据。现有 RTL 与历史 N12 DC 证据见 [实现合同](verilog.md)；新专用 E 单元的 RTL/DC 证据见 [E64 报告](../../../../test/results/e64-v1.5.8.md)，真实负载功耗仍待实施。

E64 的三格式各 961 笔均匹配保存的多精度结果及独立精确数学结果，最大 ULP=0；6 项 E 专用单测覆盖独立逐级 Fraction 等式、全部 nibble 乘积/HiF4 元数据组合、特殊值/scale、K4/8/16 与窗口、L8/L9 和真实在途周期。普通运行的配置、指纹与摘要保存在 test/runs/cmodel/，按滚动保留规则管理。本次环境缺少可链接的 ASan 运行库，未完成 sanitizer 验证；历史 sanitizer 结论不扩大到新 E 实现。E RTL 已按独立模块与专用 cutpoint 接入共用回归，不以 CModel 通过替代 RTL 仿真。

## 7. 与 RTL 对应的设计族组织建议

当前维持一个模型工程和统一 evaluate/Pipeline 入口，已新增 lane/lane_e.cpp、group/group_e.cpp，并把公共 S5 完成及 S6–S8 从 group.cpp 抽到 top/backend.cpp；保留原多精度文件名和共同基础函数。以下更完整的目录分层仍是后续迁移目标，不代表全部已经搬移：

~~~text
src/cmodel/
├── include/dp/              # 公共请求/结果/token 与配置 API
└── lib/
    ├── common/              # 格式、整数算术、解包与特殊值
    ├── lane/
    │   ├── multi/           # 多精度前端阶段
    │   └── e/               # E pair/树/e2 融合阶段
    ├── group/
    │   ├── multi/           # 多精度组阶段
    │   └── e/               # E 组阶段
    ├── top/                 # 公共后端阶段与 profile 组合调度
    └── json_io.cpp          # 公共序列化入口
~~~

公共层复用 Big/Token/Special、位宽检查、scale/C 解码、规约和 FP32 舍入。multi/e 前端拥有各自的阶段状态与 trace，在 S5 产出公共 Token；类型差异集中在前端调度点，不在每个公共算术函数中散布 profile 分支。使用简单的具名结构和函数，不为每个精度建立深层继承框架。

已抽出的公共后端保持原多精度配置的行为和周期。E 路径使用真实 S2 pair/S3 规约/S4 组和/S5 scale 阶段；每拍推进实际阶段，非预先计算后延迟输出。frontend 在构造 Config 时确定，每笔请求继续携带 datatype。

src/configs/dp/e64.json 是参数化 E CModel 入口。当前固定混合 profile 已通过 Config 调度 multi/E/QE 组，见 [混合合同](../dptop/mixed-precision-expansion.md)；不支持任意用户输入 groups 列表。新增固定四组 e64/q32e64 分别映射 E/QE 数值前端，配置为 e64_top.json/q32e64_top.json，强制 K16/L8，公共后端不复制。详见 [低精度顶层合同](../dptop/low-precision-tops.md)。

数学 reference 与原始输入数据共用一份，按实际输入、模式 K 和 scale 关系计算精确数学结果；各 profile 的有限位宽架构期望、周期记录与内部 cutpoint 分别生成。禁止用 E 的新 trace 覆盖多精度 expected 作为绕过验证的方式。内部字段允许不同，先检查各自 RTL/CModel，再按数值坐标映射对照公共 S5/S6 边界及最终输出。数学 oracle 保持独立，不直接调用被测 CModel 的算术函数。

测试入口按 profile 选择对应模块与观测适配，共用数据读取、事务协议、参考和结果统计；每个新 profile 独立记录覆盖及导出/验证证据，单一配置通过不代表整个设计族通过。

## 命名与可追溯字段

内部使用 `config/state/datatype/format_info`，分别用 `exponent_field`、`fraction_field`、`fractional_bits` 区分编码字段与定点精度。`State` 的 `operands_a/operands_b/group_max_exponents/e_frontend/c_token` 表达具体职责，Token 使用 `leading_zero_count`。E 文件名为 `lane/lane_e.cpp` 与 `group/group_e.cpp`。请求的数学操作数 a/b/c 以及已有 JSON trace 的 m/e/f/z/r 保持协议兼容；短 JSON 键是已定义的序列化接口，不能作为新局部变量缩写的理由。
