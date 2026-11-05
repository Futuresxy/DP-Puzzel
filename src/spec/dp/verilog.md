> 功能：定义手写 RTL 实现映射及验证合同；范围：单 DP、Verilog 主实现与 SystemVerilog 对照、L8、源码快照；版本：v1.5.1；修改时间：2026-11-05 11:37:59 +08:00；对应代码：[dp_top.v](../../verilog/top/dp_top.v)、[dp_top.sv](../../verilog/systemverilog/top/dp_top.sv)、[dp_tb.v](../../../test/rtl_tb/dp_tb.v)。

# 单 DP 手写 RTL 实现合同

本页记录 v1.5 手写 RTL，S5 采用 [scale 合同](scale.md) 的 14×8 无符号乘法及符号旁带。主要交付采用 IEEE 1364-2005 Verilog；按用户要求保留 SystemVerilog 对照。仅实现一个 DP，未进入计算阵列。

## 1. 文件组织与实现边界

模块名和文件名统一为 `dp_<function>.v`；一文件一 module，常量及纯函数在 `.vh`。SystemVerilog 对应模块位于独立 `systemverilog/`，不能混编两个同名 module。详细文件清单分别由 `src/verilog/files.f` 和 `src/verilog/systemverilog/files.f` 固定，禁止 wildcard 混入测试或另一实现。

| 功能 / 阶段 | Verilog 文件 | 寄存归属 |
| --- | --- | --- |
| 顶层 DP、请求控制、C transport | [dp_top.v](../../verilog/top/dp_top.v) | valid/last/type S1–S8、C raw S1–S4、C S5、S6/S7/S8 |
| T2H4Q8E16 基本组 | [dp_group.v](../../verilog/group/dp_group.v) | scale S1–S4；组 token S5 |
| T1H2Q4E8 lane | [dp_lane.v](../../verilog/lane/dp_lane.v) | S1 子模块有效控制、产品 S2、叶 S3、SOP S4 |
| 固定 layout 解包/寄存 | [dp_lane_unpack.v](../../verilog/unpack/dp_lane_unpack.v) | S1 两份 E10/M16/S4；class/signaling 旁带，扩展元素视图只是连线 |
| A/B 元素解码 | [dp_operand_unpack.v](../../verilog/unpack/dp_operand_unpack.v) | 组合；S1 由 dp_lane_unpack 注册 |
| scale / C 解包 | [dp_scale_unpack.v](../../verilog/unpack/dp_scale_unpack.v)、[dp_c_unpack.v](../../verilog/unpack/dp_c_unpack.v) | 组合；分别由 group/top 注册 |
| 尾数共享 bank | [dp_mantissa_bank.v](../../verilog/lane/dp_mantissa_bank.v) | 组合；输入 mux/隔离与重构属于 bank |
| 乘法叶 | [dp_mul_unsigned.v](../../verilog/arithmetic/dp_mul_unsigned.v) | 组合；HH/HL/LH/LL 和 scale-pair 分实例 |
| 指数共享 bank / 加法叶 | [dp_exponent_bank.v](../../verilog/lane/dp_exponent_bank.v)、[dp_exponent_add.v](../../verilog/arithmetic/dp_exponent_add.v) | 组合；两套宽/窄加法器，E 共用一份 e2 和 |
| MAX | [dp_max_tree.v](../../verilog/arithmetic/dp_max_tree.v) | 组合；lane/group/global 分别实例化 |
| 局部幅值右移 | [dp_rtz_shift.v](../../verilog/arithmetic/dp_rtz_shift.v) | 组合；每 lane 四路 |
| SOP 规约 | [dp_sum_tree.v](../../verilog/arithmetic/dp_sum_tree.v) | 组合；lane/group/top 三个层级分别注册 |
| scale 注入 | [dp_scale_multiply.v](../../verilog/arithmetic/dp_scale_multiply.v) | 组合；公共 14×8 无符号，输出 22 位幅值 |
| LZD | [dp_lzd.v](../../verilog/arithmetic/dp_lzd.v) | 组合；S5 group/C、S8 output 独立实例 |
| 全局对齐 | [dp_global_align.v](../../verilog/top/dp_global_align.v) | 组合；MAX、net、符号恢复归入本模块 |
| 双向幅值移位 | [dp_bidir_shift.v](../../verilog/arithmetic/dp_bidir_shift.v) | 组合；方向 bit reversal + 一个右移核心 |
| FP32 输出 | [dp_fp32_round.v](../../verilog/arithmetic/dp_fp32_round.v) | 组合；S8 结果由 top 注册 |

各路径命名可用于后续层级统计。E pair、符号恢复、组 abs、特殊摘要与 transport 寄存器仍属于直接拥有它们的 lane/group/top；不能把它们在父子统计中重复计数。没有为了统计添加 `dont_touch`、时钟域或额外寄存级。28/40 的工艺映射、面积与功耗待测。

S1 每侧实际复用两份 E10/M16/S4 寄存器，按 T/H/Q/E/INT8 打包和展开；没有为各格式单独保存一套宽尾数。分类旁带独立，TF32 只启用第一个 atom。M/E/S 布局也纳入 CModel 断点比对。

## 2. 参数与数值坐标

构建参数为 `K_FP16`、`LOCAL_W`、`GLOBAL_W`。分别对应 CModel 的 `k_fp16`、`local_shift_mag_width`、`global_signed_align_width`。两套 RTL 只开放 L8；L9 仍是 CModel 探索选项。默认 K16/28/40。LOCAL_W 与 GLOBAL_W 可独立调整，要求 LOCAL_W≥27、GLOBAL_W≥max(LOCAL_W+4,33)。中间模块从父层参数派生树宽、补零、LZD/指数控制及各模式 SxIxFx，DSE 直接修改窗口参数。

| 派生量 | 公式 |
| --- | --- |
| 基本组数 | `G=K_FP16/GROUP_H`，`GROUP_H=4` |
| 局部 TC 叶宽 | `LOCAL_W+1` |
| lane SOP | `LOCAL_W+1+ceil(log2(Q_LANES))` |
| group SOP | `lane_width+ceil(log2(LANES))` |
| S5 幅值 | `group_width−1`，符号独立 |
| 全局幅值 / 浮点 F | `GLOBAL_W−1` / `GLOBAL_W−2` |
| 最终 SOP | `GLOBAL_W+ceil(log2(G+1))` |
| LZD 计数 | `ceil(log2(magnitude_width+1))` |
| anchor | 根据可表示的最小实际指数/最大 raw anchor 推导最小有符号宽度；默认 10 |

自然树支持单项和非二次幂项数，奇数叶在下一层显式符号扩展。默认最终扇入 5，K4/K8 分别为 2/3；宽度不会因向上取整的树形组织丢失进位。

S5 仍为 `value=(-1)^sign × magnitude × 2^(A_raw-(M-1))`。不同格式 F 在 `A_raw=alpha−F+(M−1)` 中吸收；S6 不能再次扣 F。`e=A_raw−z` 只用于比较，原幅值先静态低补零，再按 `A_raw−E_max` 做一次双向移位。详见 [逐级格式](stage-formats.md)。

格式字段、bias、枚举和 FP4 编码表属于固定数值合同，不能把任意改编码包装成普通窗口扫参。位宽下界、K 和派生关系在仿真构建中检查；不合法配置不得用于导出或 PPA。

## 3. 控制、复位与低活动

采用同步高有效 `reset`，全局同拍作用于所有流水有效位，清除 last/type 控制并取消在途结果。数据通路无需复位到零；只有有效请求进入本级时才更新数据寄存器。复位沿上的旧输出不能被下游作为有效事务消费。

三路原子 ready、逐请求 type、无输出背压和 last 透传完全遵循 [接口](interface.md)。缺失输入只产生 bubble，不冻结已接受请求。非法 datatype 元组不握手；合法 NaN/Inf 必须按正常 L8 输出。

S2 bank 对未使用乘法器输入清零；T 只使用一套，BF16、Q、INT 按路由隔离其余单元。S5 scale 单元仅在 NVFP4/HiF4 模式使能。幅值乘法与旁路共享组和 abs，符号与幅值同拍注册。INT8 在 S6 旁路指数移位，并在 S8 旁路浮点舍入；所有格式仍为 L8。

## 4. 验证、导出与范围

[纯 Verilog TB](../../../test/rtl_tb/dp_tb.v) 直接读取 `DP_INPUTS_V1`。两版分别通过 Verilator 编译/仿真，另外以 Icarus 验证纯 Verilog 语法及四态行为。验证必须区分：对 CModel 位精确一致、相对独立数学参考的精度、RTL 时序/PPA；本轮仅前两类已有模型/仿真证据。

验证前冻结源到 `hw/rtl/DP_<implementation>_<fingerprint>/`，每个源文件标识 `RTL_ID`。清单记录源码及快照 SHA、顶层、格式常量、参数化状态和验证范围。实际参数、工具、测试输入/输出及断点计数记录在回归摘要；快照仅在对应检查通过后标为 passed；完整回归经新版后端门禁复核后才生成验证回执并设置 `ppa_eligible=true`，部分/失败回归仍为 false。此快照是参数化源码，不冒充完成综合的特化网表。

Verilog 的 `lane_fraction` 使用 datatype 对常量进行选择，避免对运行时 `elements(t)` 调用 DC 不接受的 `$clog2`；各编码的 F 值与原公式相同，未改变截断或流水。

`python3 test/run_verilog.py --implementation verilog --phase all --local-w 29 --global-w 33` 可验证自选窗口。K16 固定向量使用同配置 CModel 重新生成有限位宽期望，数学参考仍来自同一批向量的精确结果。混合回归另外覆盖 K4/K8/K16 的树深和流水断点。

测试配置和笔数见 [RTL 验证报告](../../../test/results/verilog-v1.4.md)。N12 TT DC 结果对应历史 27/40 配置，见 [时序分析](../../../hw/dc_syn/records/dp_n12_timing_20261105.md)。

## 5. 修订记录

| 版本 | 时间（+08:00） | 修改 |
| --- | --- | --- |
| v1.4.2 | 2026-11-04 23:05:38 | 新增单 DP Verilog 实现和 SystemVerilog 对照映射，落实同步复位与 L8；增加标准 Verilog TB、快照和 Verilator 验证。数值合同不变。 |
