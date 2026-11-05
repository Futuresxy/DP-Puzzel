> 功能：定义 DP CModel、模块映射及共用测试接口；范围：分组共享 DP 的整数数值、逐周期执行、精度参考及证据边界；版本：v1.4.4；修改时间：2026-11-05 11:20:02 +08:00；对应代码：[模型 API](../../cmodel/include/dp/model.hpp)、[参数](../../cmodel/include/dp/config.hpp)、[执行器](../../cmodel/lib/model.cpp)、[测试入口](../../../test/run_cmodel.py)；Chisel/手写 RTL 未实现。

# DP CModel 合同

用户已授权在现有 spec 上实现 CModel，并要求原九格式优先测试、随后扩展 TF32/INT8。模型实现当前分组共享方案；独立一次对齐、专用 Q/E/QE 增源、阵列和 EDA 不在本批范围。默认 T8H16Q32E64、L8、II=1。模型不以宿主 float/double 代替有限位宽运算。

## 1. 实现与模块映射

| 文件（相对 src/cmodel/） | 责任 / 硬件对应 |
| --- | --- |
| include/dp/config.hpp、lib/config.cpp | 集中格式常量、配置及自然位宽/树深派生；合法类型和输入约束 |
| include/dp/model.hpp、lib/detail.hpp | 请求、结果、flags、逐级状态与 group token |
| lib/unpack.cpp | S1 A/B/scale 解包为 E/M/S 与分类；S5 C 解包辅助 |
| lib/lane.cpp | T1H2Q4E8：S2 乘法重构/指数和/MAX，S3 幅值 RTZ/E pair，S4 lane 树 |
| lib/group.cpp | T2H4Q8E16 的 S5 合并/scale/abs/LZD；顶层 S6 双向对齐、S7 树、S8 RNE/INT32 |
| lib/arithmetic.cpp | 整数宽度断言、平衡加法树、RTZ、RNE、特殊值摘要 |
| lib/model.cpp | 事务 evaluate 与逐级 Pipeline；二者使用同一 stage 函数 |
| lib/json_io.cpp、main.cpp | JSONL 协议、固定宽度 hex/枚举检查、CLI |

C++ 使用 Boost cpp_int 保存精确整数，**在规定截断点显式 RTZ，在其他出口检查位宽**；大整数不代表硬件具有无限宽窗口。每个 occupied stage 在 step 中只前进一级，没有提前算完再延迟输出。软件保留旧字段/trace 是诊断便利，不作为 RTL 寄存器数或 PPA 估算。

## 2. 参数合同

四项可配置量：k_fp16（4/8/16），local_shift_mag_width（默认 28、至少 27），global_signed_align_width（默认 40），post_scale_norm_extra_stage（0/1，默认 0）。配置是显式 JSON 对象；未知键、负数、小数、溢出值及非法组合报错，不通过环境变量隐式修改数值。

其他量由参数派生：G=K/4，leaf=local+1，lane=leaf+ceil_log2(4)，group=lane+ceil_log2(2)，group_mag=group−1，global_mag=global−1，sum=global+ceil_log2(G+1)。要求 global_mag≥max(group_mag,32)，所有静态 pad 非负。当前窗口扫描是建模探索，不把允许构建的每个窗口宣称满足用户 35/37 位精度目标；默认及已测配置单独记录。

格式常量、E guard、scale 窗口和每模式 F 见 [数值布局](numeric-layout.md)、[逐级出口](stage-formats.md)。S2 raw 元素指数不去 bias；S5 形成无偏原 anchor。C 同样在 S5 去 FP32 bias。S6 用 signed 真实指数 MAX 和完整 unsigned d；S8 仅为最终 FP32 编码加一次 127。

NVFP4/HiF4 固定共享 **signed15×positive signed9**，公共 raw24/useful23，详见 [scale](scale.md)。S5 乘法完成后取幅值/LZD 计数，不左移；S6 net=z−d 一次双向移位。模型逐笔携带控制，last 只透传。

## 3. 逐级数值与周期 API

`evaluate(config, request, trace)` 返回一笔完整结果。`Pipeline(config, trace).step(request, a_valid, b_valid, c_valid, reset)` 返回本时钟沿前可见输出，再推进各级。三路都有效、类型元组合法且非 reset 时原子接收；气泡和非法类型不阻塞在途结果。全局 reset 丢弃全部在途请求。

沿 n 接收，S1 在 n 更新，S8 在 n+7 更新，step(n+8) 返回结果，因此报告 L8。每拍均可接收，输出无 ready。可选 L9 的 S5 仍完成 scale/abs/原 anchor/C 解包，新增一级只做 LZD，后三级整体顺延；默认测试数据和期望采用 L8，L9 仅作数值/寄存边界探索，未因模型存在而自动选择 RTL L9。

`id` 为验证器侧关联编号，不新增 DUT tag 端口。`protocol_error` 为驱动诊断，不新增 DUT 错误端口。all_valid 下非法类型拒绝握手；超宽数据、TF32/FP6 非零填充、错误 scale 广播/负 NV scale 等源违反 payload 合同会抛异常，且在周期状态更新前检查。partial-valid 时不解读无效请求内容。

trace 的每个 cutpoint 有 stage、operation、data。覆盖 S1 每元素及 packed E/M/S、S2 magnitude/exponent/F/r、S3 signed leaves/移位差、S4 lane SOP/F、S5 raw group/C token 与共享 scale 乘法操作数、S6 E_max/z/d/net/对齐值、S7 总和/F、S8 输出。token 保留 sign、m、width、F、anchor_raw、z、派生 e 与 zero/special。整数和特殊值未使用的浮点控制是安全占位，不作为数值指数。

模型可检查范围/等式和周期边界；逻辑阶段不能证明实际组合延迟符合 1.41GHz。S2 MAX 回传、S5 scale→LZD、S6 MAX→双向移位、S8 norm/RNE 都仍须 RTL/工艺时序验证。

## 4. 特殊值、舍入和诊断

已确认 canonical qNaN=0x7fc00000、RNE、渐进下溢、舍入后 tininess。精确抵消为 +0，仅所有零项为负时保留 −0，最终微小负数舍入零保留负号。sNaN、0×Inf、异号 Inf 求和的 invalid 不因另一项 NaN 被屏蔽。见 [特殊值合同](special-values.md)。

结果 flags 仅供验证：invalid、overflow、underflow、inexact 为已定义有限路径的异常诊断；local_truncated/global_truncated 分别记录两次 RTZ 丢位。S8 inexact 不等价于理想点积相对输出的全程 inexact；不把早先丢位重新注入最终舍入。INT32 内部精确求和，输出模 2^32，另记 integer_overflow。

## 5. 同一份激励与两类参考

规范化输入是 [DP_INPUTS_V1](../../../test/data/README.md)，位布局对应 [DP 顶层接口](interface.md)。九格式来自旧 correct_961，只导入新版要求的 K，不导入旧阈值/通过结论。原文件只读，SHA256/原始五段来源记录在每份 manifest。TF32 K8/INT8 K32 固定种子构造后使用同一 layout。

1. C++ 对独立 Python Fraction **有限窗口参考**逐位比较：后者在实数 dyadic 坐标按局部/全局网格 RTZ，不复用 C++ 的容器落位、部分积重构或 z−d 代码。
2. 对无限精度 Fraction 点积加 C 后一次 FP32 RNE 计算 ULP/绝对误差；不要求已截断架构全部逐位相等。对每个实际丢位项，累加一次局部量化单位乘 scale 绝对值，加每个全局丢位项的量化单位，再加最终半 ULP，得到每例可计算的绝对误差上界。数值接近零时 ULP 可放大，不用固定宽松 ULP 门槛掩盖误差。
3. TF32 另记录 FP64 math.fsum 参考。它是近似；精确边界/负零由 Fraction 独立复核并记录差异 ID。INT8 必须与无界整数参考（含 C 和回绕）完全一致。

`expected.jsonl` 来自已通过独立检查的 CModel，同时保存理想数学结果。未来 Chisel RTL 与手写 Verilog 必须逐位对齐其中 d/type/last，并按相同周期事件检查 valid；不能用数学误差阈值放宽 RTL 对 CModel 的一致性。

## 6. 验证和剩余边界

执行说明见 [CModel](../../cmodel/README.md)；首批结果见 [报告](../../../test/results/cmodel-v1.4.md)。单测覆盖 K4/K8/K16、2/3/5 项树、三组窗口、L8/L9、相邻换型、reset、气泡、无效类型、输入填充/广播、small-code 与 scale 编码、特殊值/RNE 边界、INT 极值及回绕。只对已列组合作覆盖声明；不是所有 A/B 编码笛卡尔积穷举。

三实现使用共同数学合同，但 C++ 文件不等于最终 RTL module 一一结构实例化；operand isolation、时钟门控、mux 门级共享和面积归属仍须实现和综合证据。当前无新版 RTL 仿真、DC 或功耗结果。
