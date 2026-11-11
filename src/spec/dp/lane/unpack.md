> 功能：定义固定 E/M/S 解包数值布局；范围：T/H/Q/E、HiF4 e1/e2 和 E6M2 块 scale；版本：v1.7.1；修改时间：2026-11-09 01:00:00 +08:00；对应代码：[CModel lib/unpack.cpp](../../../cmodel/lib/unpack.cpp)、[dp_lane_unpack.v](../../../verilog/unpack/dp_lane_unpack.v)、[dp_lane_operand_unpack.v](../../../verilog/unpack/dp_lane_operand_unpack.v)、[dp_unpack_atom.v](../../../verilog/unpack/dp_unpack_atom.v)；Chisel 尚未实现。

# 固定 E/M/S 解包布局

状态：依据用户 2026-11-04 提供的解包图，固定字段、H/T 尾数位号与 Q 重编码方向已确认。用户明确指定参考历史解包的 HiF4 S1P2、e1/e2 和 E6M2（bias=48）定义；下文将其写成新版数值公式，不继承历史流水或模块组织。

## 1. 原子块、lane 与基本组

普通模式的一个解包原子块对应 16 位 packed input，容纳 H1/Q2/E4；两个原子块构成 32 位逻辑 lane，容纳 H2/Q4/E8。两个 lane 构成 T2H4Q8E16 基本组。TF32 是例外：一个元素占完整 32 位容器，一个 lane 只产生一个 T 元素；不能把两个 16 位半字解释为两个 TF32。

每侧 A/B 独立输出相同形状的 `E[9:0]`、`M[15:0]`、`S[3:0]`。H 模式每个原子块使用一个元素字段，Q 使用两个，E 使用四个。T 模式每个 32 位 lane 使用一个这样的字段记录；另一份 H/Q/E 原子块资源在 T 模式不产生有效元素。以上是布局与容量映射，不要求物理复制两套解码器。

固定容器位宽用具名规格常量表示：`unpack_input_atom_bits=16`、`unpack_exp_bits=10`、`unpack_mantissa_bits=16`、`unpack_sign_bits=4`。原子块数、lane 数、元素索引和 K 配置从容量关系派生，不能为 K16 写死实例数量。

## 2. 字段与小数点

`M` 存储无符号幅值，符号由 `S` 单独保存；`IuFv` 表示 u 个整数幅值位和 v 个小数位，不含符号。整数 coefficient `m` 的数值为 `m × 2^(-v)`。同一 M 容器允许不同格式的二进制小数点，不表示不同格式具有相同缩放坐标；后续指数补偿必须显式计入 v。

| 模式 | E 布局 | M 布局 | S 布局 |
| --- | --- | --- | --- |
| TF32 | `E[7:0]=e0`，`E[9:8]=0` | 一个 I1F10：`M[10:0]={h,F[9:0]}`，`M[15:11]=0` | `S[0]=s0`，其余为 0 |
| BF16 | `E[7:0]=e0`，`E[9:8]=0` | `M[7:0]={h,F[6:0]}`，I1F7；`M[15:8]=0` | `S[0]=s0`，其余为 0 |
| FP16 | `E[4:0]=e0`，`E[9:5]=0` | 同 T 的 I1F10：`M[10:0]={h,F[9:0]}`，`M[15:11]=0` | `S[0]=s0`，其余为 0 |
| MXFP8/6 | `E[4:0]=e0`，`E[9:5]=e1`，各为重编码后的 5 位指数 | `M[3:0]=m0`、`M[7:4]=m1`，各 I1F3；`M[15:8]=0` | `S[1:0]={s1,s0}`，其余为 0 |
| MXFP4/NVFP4 | `E[9:0]=0`，元素指数已融入 M | `M[4*i+:4]=mi`，i=0..3，各 I3F1 | `S[i]=si`，i=0..3 |
| INT8 | `E[9:0]=0` | `M[7:0]=abs(x0)`、`M[15:8]=abs(x1)`，各 I8F0，包含 abs(-128)=128 | `S[1:0]={s1,s0}`，其余为 0 |
| HiF4 | `E[0]=e2`，`E[9:1]=0`；e2 为共享的 1 位指数增量 | `M[4*i+:4]=mi`，i=0..3，各 I2F2；e1 已融入 mi | `S[i]=si`，i=0..3 |

未使用字段统一置零，不依赖 Don't-care/X；只有由 mode 决定的活动元素参与分类与求和。图中的 unused 与补零在逻辑输出上均为零。E 只是紧凑布局，不能作为一个 10 位指数直接相加；Q 必须拆成两个字段，H/T 必须按自身指数基准解释。

**已澄清图注**：TF32 B 行的 F7 按 S1/E8/F10 和 A/B 对称规则更正为 F10。用户明确选择 TF32/FP16 按格子落位，即 I1F10，不在低位追加零；图中的 I1F11 文字公式不采用。MXFP8/6 统一转内部 E5M3，MXFP4/NVFP4 仍转 I3F1。

## 3. T/H 的字段解码

TF32 外部字段为 `s=x[31]`、`e=x[30:23]`、`F=x[22:13]`，`x[12:0]=0`；FP16 为 S1/E5/F10，BF16 为 S1/E8/F7。TF32 用 FP16 族尾数通路和 BF16 族指数通路，不额外执行 FP32→TF32 量化。低填零位是输入合同约束，非法填充值的报错方式待验证接口确定。

先按原始格式分类，再恢复 hidden bit：有限正规数 h=1，零/非正规数 h=0。非正规数的有效指数使用 `1-bias`，不得把存储 e=0 当作正规指数 `0-bias`。NaN/Inf 不靠 h/M 值表达，单独传递分类。T/H 的 E 输出采用有效偏置指数：有限数 `E=(raw_e==0 ? 1 : raw_e)`；NaN/Inf 的数值字段安全占位为 E=1、M=0。对有限数，`x=(-1)^S × M × 2^(-fraction_bits) × 2^(E-bias)`，其中 T/FP16 的 fraction_bits=10、BF16 为 7；T/BF16 bias=127、FP16 bias=15。

正规 FP16/TF32 的 1.0 映射为 coefficient 1024，乘 `2^-10` 还原 1.0；BF16 的 1.0 映射为 128，乘 `2^-7` 还原 1.0。T/FP16 两个幅值相乘后有 20 个小数位，BF16 有 14 个；指数偏置与求和增长位另外计算。

## 4. Q 的 E5M3 共用表示

外部 FP8 子型为 E4M3/E5M2，FP6 子型为 E3M2/E2M3。FP6 仍占 8 位槽，先取 `[7:2]` 的六个有效位，不能把低两位补零视为额外数值精度。各原子块元素 0 位于低字节，元素 1 位于高字节。

图中的“recode to E5M3”是内部 5 位指数 + 4 位 I1F3 幅值 + 独立符号，不是把外部数重新舍入成一种 9 位标准浮点编码。两位 fraction 扩展至三位时在低位补零，三位 fraction 原样保留。指数必须补偿原始 bias 和任何非正规数处理，满足 `decoded_value == original_value`。

共同 5 位指数采用 bias=15。对有限编码，设原始指数 e、fraction f、fraction 位数 fbits、原格式偏置 B：

```text
h = (e != 0)
e_effective = (e == 0 ? 1 : e)
e_out = e_effective + (15 - B)
m_out = ((h << fbits) | f) << (3 - fbits)
x = (-1)^s × m_out × 2^(-3) × 2^(e_out - 15)
```

| 子型 | 原始 B | fbits | 指数平移 | 尾数低位补零 |
| --- | ---: | ---: | ---: | ---: |
| E5M2 | 15 | 2 | 0 | 1 |
| E4M3 | 7 | 3 | 8 | 0 |
| E3M2 | 3 | 2 | 12 | 1 |
| E2M3 | 1 | 3 | 14 | 0 |

上述只是 bias 坐标平移和零扩展，有限输入不发生舍入，subnormal 以 h=0 保留。零可以保留其格式对应的有限占位指数，但 m=0；NaN/Inf 使用旁带，数值字段采用安全占位值（本合同选 e_out=1、m_out=0），不能从内部 E 全 1 再分类。 用户确认首版 A/B 仅同格式，独立 datatype 字段按 [接口矩阵](../dptop/interface.md) 检查。

## 5. E2M1 到 I3F1 的无损转换

图中 MXFP4/NVFP4 元素均为 S1/E2/F1。按 E2M1 值表，幅值集合为 `{0,0.5,1,1.5,2,3,4,6}`，可精确变换为四位 coefficient `{0,1,2,3,4,6,8,12}`，即 `mi = 2 × abs(value_i)`，I3F1。完整值表依据 [OCP MX v1.0 §5.3.3](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)，NVFP4 在此采用用户图中相同的元素编码，其块 scale 另定义。

该转换不包含块 scale，不发生元素值舍入；负号和负零符号保留在 S。两个 I3F1 幅值乘积的小数位为 2，单个幅值乘积按自然 8 位承载，再显式注入符号与规约增长。元素 E=0 不表示块 scale=1。

## 6. HiF4 到 I2F2

按图将第一级因子 e1 融入每个四位 I2F2 幅值，保留共享 e2 供后续指数/缩放处理；外部块 scale 仍独立存在。e1 只能应用一次，不得在 S1 融合后又在 S5 重复乘入。

用户确认 S1P2 是一位符号、一位整数、两位小数，共四位：`s=data[3]`，`u=data[2:0]` 为 I1F2 的无符号 coefficient，元素值为 `(-1)^s × u/4`，包含零及负零。e1、e2 各 1 位，分别表示局部的 `2^e1`、`2^e2` 因子。

```text
e1_index = floor(i / 4)     // 每 4 个元素共享
e2_index = floor(i / 8)     // 每 8 个元素共享
mi = u << e1[e1_index]      // 4 位 I2F2 coefficient
E = zero_extend(e2[e2_index], 10)
x_i = (-1)^s × mi × 2^(-2) × 2^e2[e2_index] × block_scale
```

`mi` 最大为 7×2=14，四位可精确容纳；支持的幅值最大 3.5，步长至少 0.25，所有 u∈[0,7]、e1∈{0,1} 都无损。上界 3.75 是 I2F2 容器范围，不是所有合法 HiF4 编码都会取到。两个 I2F2 幅值乘积有 4 个小数位，乘积 coefficient 按自然 8 位承载；e2 只作为剩余指数增量，不能重复乘入 e1。

每 16 E 项含 4 个 e1、2 个 e2，恰好对应四个原子块及两个 lane。索引按连续元素划分，与用户指定的 `sf_group0(i)` / `sf_group1(i/2)` 解包相同。

## 7. HiF4 块 scale：E6M2，bias=48

每侧块 scale 为 8 位无符号 E6M2，`e=scale[7:2]`、`f=scale[1:0]`，没有 sign。除 0xff 为 NaN 外，数值为 `block_scale=(1+f/4) × 2^(e-48)`，hidden bit 恒为 1；不设零、Inf 或 subnormal 编码。特别地，0x00 是 `2^-48`，不能按 IEEE 有符号浮点的 exponent=0 规则解码为零。

若共用内部 scale 的 bias=127 指数与 I1F3 幅值，可无损输出 `scale_exp=e+(127-48)`、`scale_mant={1,f[1:0],0}`；NaN 使用独立分类及安全占位。A/B scale 各自独立，主配置同侧块 scale 广播四份不意味着 A/B scale 相同。

以上为本项目经用户指定的历史解包语义，来源：[DataUnpack_E](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/pe/PE_E/DataUnpack_E.scala)、[DecodePrimitives.unpackHiF4/unpackSF](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/Utils/DecodePrimitives.scala)、[metadata 位宽](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/Utils/Interfaces.scala)、[FPBias.e6Bias](https://github.com/Futuresxy/DP-Puzzel/blob/5f53f19877e1f4750aaf1688b8ecb84c598ee8bc/hw/legacy/chisel_src/config/Parameters.scala)。仅采用这些明确的字段/数值定义，不采用历史 11/18 级流水、保留窗口或模块命名。

## 8. 分类旁带与后续共享

E/M/S 之外保留每个活动 A/B 元素的分类信息，scale 按自身格式分类；A/B/scale 分类发生在 S1，FP32 C 分类在 S5 发生，INT32 C 不执行浮点分类。所有摘要与本笔 ctrl 继续传到结果选择。分类规则见 [特殊值](../common/special-values.md)。

固定布局方便共享乘法器位片及指数运算，不自动确定硬件复制数、subword 乘法交叉项屏蔽或加法树位宽。

INT8 采用有符号输入，S1 转独立符号及八位无符号幅值；与 Q 共用乘法器/规约，数值坐标按整数另行派生。

## 9. A/B/scale 的 S1 解包与 C 的 S5 解包

S1 解包 A/B/scale；A/B 仍为既定 E/M/S 布局。C 与它们同拍接收，但 S1–S4 仅保存原始 32 位编码及本笔 c_datatype，S5 并行解包：FP32 为 sign、M24={h,F23}、有效指数和分类；INT32 为独立 sign 和安全 M32 幅值（包含 INT32_MIN）。C 的数值/时刻见 [出口表](../common/stage-formats.md)。

scale 的 E8M0/E4M3/E6M2 统一解包为 E8 指数、I1F3 幅值和分类，详见 [scale 合同](../group/scale.md)。E/M/S 布局与 HiF4 e1/e2 位号按本页定义；新乘法器必须按当前 Q 的 M[7:0] 提取两个 nibble，不能照抄历史 M[11:8] 的路由。

参数的取值与推导统一进入 Chisel 构造参数对象，计划入口 src/chisel/parameter/（未创建）。

## 10. datatype 与解包边界

C 的 S5 物理输出统一为 sign+M32：FP32 自然 M24/F23 在低位补 8 零，成为 I1F31；INT32 为 I32F0。FP32 额外低零可由综合常量优化，不改变数值、A_c 或流水级数。

各侧 datatype 在原子 req_fire 时采样；首版 A/B 同格式，具体枚举/scale 合法矩阵见 [DP 接口](../dptop/interface.md)。S1–S4 的 C 存储无需保存解包后的重复 sign/exp/mant/class；节省的是展开记录的额外寄存位，原始 C32 与类型仍须保存。S5 解包不减少 C 延迟，不延后外部接收。

## 11. 当前纯 Verilog 的紧凑接口

`dp_lane` 实例化一个 A/B 入口 `u_lane_unpack`，入口内部有两份 `dp_lane_operand_unpack`。单侧模块实例化两份 `dp_unpack_atom`，按格式固定取位、分类并直接生成 M16/E10/S4，再用原 `ff_s0_s1_*` 保存。`dp_top` 活动路径不再实例化通用 `dp_operand_unpack`，不经过逐元素宽字段解码后重新打包。

| dp_lane_unpack 输出 | 每侧/总宽度 | 消费者与语义 |
| --- | ---: | --- |
| out_a_mantissas / out_b_mantissas | 每侧 32 | 两个 M16，直接送 dp_mantissa_bank |
| out_a_exponents / out_b_exponents | 每侧 20 | 两个 E10，直接送 dp_exponent_bank |
| out_a_signs / out_b_signs | 每侧 8 | 两个 S4；入口内部先选槽再做符号 XOR，lane 保留观察连线 |
| out_product_negative | 8 | S2 逐乘积符号，未用槽为零 |
| out_product_active | 8 | S2 有限非零乘积掩码，供指数 MAX 使用 |
| out_special | 4 | S2 NaN、invalid、正 Inf、负 Inf 摘要 |
| out_all_negative | 1 | S2 所有参与项均为负，包括零乘积 |

端口的 M/E/S 来自 S1；分类配对和归约仍在 S1 后的 S2 组合段，由 `dp_lane` 原 S2 DFF 捕获。`in_datatype` 解码当前输入，`in_registered_datatype` 必须与 S1 字段同拍，不能用下一笔格式解释已寄存 payload。valid 每拍推进，payload 只在 `rst_n & in_valid` 更新；复位和气泡保持原合同。

每个 atom 在 M16/E10/S4 外另存四个 2-bit class 和四个 signaling bit，因此单侧 S1 payload 声明宽度为 `2×(16+10+4+8+4)=84` 位。重构前后相同；综合可优化其中的常量字段。删除的每侧 `8×23=184` 位 Number 是组合展开接口，不能将接口减少直接计为 DFF 或面积收益。

特殊值必须先对同一元素的 A/B 配对，再做 lane 归约：

- 任一 NaN 置 NaN 摘要；sNaN 或该元素 `0×Inf` 置 invalid。
- Inf 乘积需排除 NaN 与零，其符号取 A/B XOR；lane 同时含正、负 Inf 时置 invalid。
- 只有双方 class 均为 FINITE 的元素参与有限非零指数 MAX。
- all_negative 包含正/负零的符号，未用槽作为归约与的 1。

单侧 class/signaling 保留元素位置，仅在入口内部使用，不向数值 bank 传递。bank 只按本页位号选择系数或指数，不再判定原编码的 hidden bit、subnormal、NaN/Inf；特殊值数值占位也只由元素译码器生成。

实现组织参考 `Quant_LLM_Chip_Codesign/HW/PE/PEGroup/DataUnpack.scala` 的字段分离与 A/B 配对摘要，数值布局保持本 DP 合同：FP16/TF32 为 I1F10，Q 两个 nibble 位于 M[7:0]，scale 仍由 group 负责，L8/II=1 不变。紧凑接口的原验收见 [紧凑解包验收](../../../../test/results/dp-compact-unpack-v1.6.4.md)；固定格式实现及同约束综合对比见 [固定解包验证](../../../../test/results/dp-fixed-unpack-20261109.md)。

## 12. 固定格式直接打包实现

`dp_unpack_atom` 每份对应单侧一个 16 位 atom。格式生成循环仅组织源码：
`EXP_FIELD_W`、`FRACTION_W`、`RAW_LSB` 等全部为生成期 localparam，不是运行时
信号。每个候选固定提取原编码、恢复 hidden bit、判定 Zero/Inf/NaN/sNaN，并直接
写入第 2 节约定的 M/E/S/class 槽；互斥 datatype 掩码选择候选，无匹配时输出零。

- TF32 固定读取 `[31:13]`，仅 atom0 有效；atom1 全零。
- FP16/BF16 固定读取对应半字；Q 固定读取两个字节，FP6 固定去掉低两位 padding。
- Q 的 F2→F3 通过低位拼零，bias 补偿为固定小位宽常量加法。
- MXFP4/NVFP4 共用 E2M1 coefficient 表；HiF4 e1 用两种固定拼接选择，e2 写 E[0]。
- INT8 每 atom 两项，保留 abs(-128)=128。基线支持集合不减少。

本次只改变组合解码组织。S1 的 M/E/S/class/sNaN 寄存布局、精度门控、S2 的 A/B
配对特殊摘要及 L8/II=1 不变；不能把组合中间连线减少计作寄存器节省。特殊值在解包内
判定，但本次没有把 S2 配对逻辑提前到 S1，也没有手动删改分类旁带寄存器声明；综合可裁剪由固定布局显式确定的恒零位。

CModel 数值语义不变，不需更新 golden。共享该前端的混合顶层会继承代码变化；本批
功能和 DC 验收限定为 `dp_top`，其他顶层的旧网表仍对应其旧快照。
