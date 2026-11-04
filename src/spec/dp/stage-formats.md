> 功能：列出每级数值出口的定点格式与指数范围；范围：S1–S8、同格式 A/B、C 的 S5 解包、anchor 与 SOP；版本：v1.4.2；修改时间：2026-11-04 23:42:09 +08:00；对应代码：[CModel lib/detail.hpp](../../cmodel/lib/detail.hpp)；分组主方案手写 RTL：[dp_top.v](../../verilog/top/dp_top.v)；Chisel 尚未实现。

# 每级 anchor、SOP 与 SxIxFx

状态：本表展开 [位宽推导](numeric-layout.md) 的默认配置，供架构审阅。用户已确认首版 A/B 同格式、逐请求 datatype 控制及 C 在 S5 解包。数值范围是算术推导，不代表误差或 1.41 GHz 已验收。参数改变时重新生成这些结果，不能把表内数字复制为模块常量。

## 1. 记号和数值坐标

- `S1IiFf` 的一位 S **不包含在 I 内**，总数值位宽为 `1+i+f`。`SM` 指独立符号加无符号幅值，`TC` 指二补码；两者不能直接按位互换。
- `S0IiFf` 为无符号 coefficient。SM 的 S 可来自独立符号线；表内位宽不包括指数、valid、datatype 或特殊值旁带，也不包括固定 E/M/S 容器中闲置的零。
- 对 TC 整数 coefficient q，实际值为 `q × 2^(alpha-F)`；对 SM 为 `(-1)^negative × magnitude × 2^(alpha-F)`。SxIxFx 描述 coefficient 的定点解释，alpha 描述额外的二进制指数。
- `r` 是基本组内有限非零乘积的最大**有效偏置指数和**；`alpha` 是去偏置并融合 scale 指数后的参考指数；`A` 是幅值容器最高物理位的权重，即 `A=alpha-F+(M-1)`。只有相同坐标的指数才能直接比较。
- S1 尚无乘积，S2 尚无 SOP，不能把它们的单元素或单乘积字段标成组 SOP。S3 只有 E pair 已是局部 SOP；S4 才产生每 lane 一个 SOP。

默认参数推导：局部幅值 `2+25=27` 位，补码叶 W28，lane W30，基本组内部补码 W31，组输出幅值 M30 加独立符号；全局有符号窗口 W40，幅值 M39。`G=k_fp16/4`，顶层树有 `N=G+1` 项。

## 2. S1：A/B/scale 解包，C 保持原始编码

| 模式 | 每侧每个活动元素的逻辑数值 | 有效指数 E（每元素） | 数值关系 |
| --- | --- | --- | --- |
| TF32 | SM S1I1F10，12 位 | U8，有限 E=1..254 | alpha=E-127 |
| FP16 | SM S1I1F10，12 位 | U5，有限 E=1..30 | alpha=E-15 |
| BF16 | SM S1I1F7，9 位 | U8，有限 E=1..254 | alpha=E-127 |
| MXFP8/6（Q） | SM S1I1F3，5 位 | U5，重编码后见下表 | alpha=E-15 |
| MXFP4/NVFP4 | SM S1I3F1，5 位 | 常量 0 | 元素指数已融入 coefficient |
| HiF4 | SM S1I2F2，5 位 | U1，e2=0..1 | e1 已融合；alpha=e2 |
| INT8 | SM S1I8F0，9 位 | 不使用 | 幅值 0..128，包含 -128 |
| 单侧 scale | S0I1F3，4 位 | U8，统一 bias=127 | scale=m×2^(E-127-3) |
| C | 原始 32 位 payload | 尚不解码 | S1–S4 携带 `c_datatype`，S5 才区分 FP32/INT32 |

E/M/S 的**物理接口**仍为每原子块 E10/M16/S4，按 [解包](unpack.md) 切片；不能把 E10 当成一条十位指数。Q 的有限有效指数范围：E5M2 为 1..30，E4M3 为 9..23，E3M2 为 13..19，E2M3 为 15..17。零/特殊数占位不参与有限非零 MAX。

## 3. S2：单乘积与基本组公共 r

| 模式 | 单乘积幅值 / 独立 sign | 每 lane 尾数积数 | 公共 r 的有限非零范围 / 最小字段 |
| --- | --- | ---: | --- |
| T | S0I2F20 W22 + sign | 1 | 2..508 / U9 |
| FP16 | S0I2F20 W22 + sign | 2 | 2..60 / U6 |
| BF16 | S0I2F14 W16 + sign | 2 | 2..508 / U9 |
| Q | S0I2F6 W8 + sign | 4 | 2..60 / U6；细分范围由子型推导 |
| MXFP4/NVFP4 | S0I6F2 W8 + sign | 8 | 常量 0 |
| HiF4 | S0I4F4 W8 + sign | 8 | 0..2 / U2 |
| INT8 | S0I16F0 W16 + sign | 4 | 不使用 |

S2 注册各项指数和与本基本组公共 r；共用 r 容器由支持格式范围推导为 U9。Q 的四个子型 r 范围依次为 2..60、18..46、26..38、30..34。T/H/Q 的 MAX 跨本组两个 lane，HiF4 比较两个 lane 的 e2 和。

scale 旁路：两侧 U8 指数和为 U9；系数积为 S0I2F6 W8。MX 系数积 64 表示 1.0，可旁路后续数据乘法。单项 INT8 合法积范围 [-16256,16384]，转补码后精确装入 S1I15F0 W16；S2 的原始无符号乘积与独立 sign 仍保留至转换，不能简单丢掉 unsigned 最高位。

## 4. S3：移位或 E pair 后的共享叶节点

| 模式 | S3 有效叶节点 / lane | S3 出口格式（TC） | alpha / r 含义 |
| --- | ---: | --- | --- |
| T | 1 | S1I2F25，W28 | r-254 |
| FP16 | 2 | S1I2F25，W28 | r-30 |
| BF16 | 2 | S1I2F25，W28 | r-254 |
| Q | 4 | S1I2F25，W28 | r-30；块 scale 尚未施加 |
| MXFP4/NVFP4 | 4 个 pair | S1I7F20，W28 | 0；块 scale 尚未施加 |
| HiF4 | 4 个 pair | S1I5F22，W28 | r；块 scale 尚未施加 |
| INT8 | 4 | S1I15F12，W28 | 0；F12 全部是结构低零 |

T/H/Q 将乘积补至 I2F25，再按 r-e_product 对幅值 RTZ，之后恢复符号。E pair 自然 W10；补两位精确保护零得到 W12，再补 16 个结构低零放入 W28。MX/NV 的 F=2+2+16=20，HiF4 的 F=4+2+16=22。HiF4 的 0/1/2 位移消耗的是预置保护零，无局部精度损失。

S3 保留的 r 与 S2 相同，公共物理字段 U9；特殊值仍走旁带。INT8 转 W16 补码后补 12 个结构低零，按整数精确通路处理。T/H 在 S4 利用空闲树层再做静态落位，不能在 S3、S4 重复补同一组低零。

## 5. S4：每 lane 一个 SOP

| 模式 | 自然 SOP 宽度 / F | 放入 W30 的低零数 | S4 出口格式（TC） |
| --- | --- | ---: | --- |
| T | W28 / F25 | 2 | S1I2F27 |
| FP16/BF16 | W29 / F25 | 1 | S1I3F26 |
| Q | W30 / F25 | 0 | S1I4F25 |
| MXFP4/NVFP4 | 紧凑 W14 / F4 | 16 | S1I9F20 |
| HiF4 | 紧凑 W14 / F6 | 16 | S1I7F22 |
| INT8 | W18 / F0 | 12 | S1I17F12 |

E/INT8 的表中补零已经包含 S3 的落位，S4 不再重复追加。所有 lane 共享 W30 物理输出，S4 的 r/alpha 与 S3 相同；部分和变零时更新 zero，不改变另一个 lane 所使用的共同 r。当前请求的 control 决定 F，不能由下一笔输入 datatype 直接驱动。

## 6. S5：scale 后原始 SOP 与 LZD 计数

两 lane 合并；NV/HiF4 均用 signed W15 SOP（F4/F6）乘 positive signed W9 scale（F6），原生 W24 取公共有用 W23（F10/F12），补 8 低零落入 W31，F18/F20 保持。无格式缩位 mux。其他浮点模式旁路；安全 abs 得到 M30 后做 LZD，仅输出 z，不左移。

| 模式 | S5 原幅值 SM 格式（sign+M30） | alpha_raw 范围 | A_raw=alpha_raw+29-F_raw | e=A_raw-z 保守范围 |
| --- | --- | --- | --- | --- |
| T | S1I3F27 | [-252,254] | [-250,256] | [-279,256] |
| FP16 | S1I4F26 | [-28,30] | [-25,33] | [-54,33] |
| BF16 | S1I4F26 | [-252,254] | [-249,257] | [-278,257] |
| Q | S1I5F25 | [-282,284] | [-278,288] | [-307,288] |
| MXFP4 | S1I10F20 | [-254,254] | [-245,263] | [-274,263] |
| NVFP4 | S1I12F18 | [-12,16] | [-1,27] | [-30,27] |
| HiF4 | S1I10F20 | [-96,32] | [-87,41] | [-116,41] |
| INT8 | S1I18F12 | 0 | 浮点字段置 0 | 不参与 |

`alpha_raw=r-bias_a-bias_b+(scale_E_a+scale_E_b-254)`，无 scale 时括号为 0。组 token 注册 `m_raw,negative,A_raw,z,zero/special,ctrl,valid/last`；默认 A_raw signed10、z unsigned5，非零 z=0..29。`value=sign×m_raw×2^(A_raw-29)`，**不是**未经移位的 m_raw 配 e。e 用于 S6 比较，逻辑上由 A_raw-z 生成；如果提前到 S5 算 e，须记录接口适配且不丢原坐标。

| C 类型 | S5 原幅值出口 | A_raw_c | z_c |
| --- | --- | --- | --- |
| FP32 | 自然 M24={h,F23}低补 8 零→SM S1I1F31，M32 | (raw_e==0?1:raw_e)-127，[-126,127] | 正规 0；非正规非零 clz24=1..23；不动态左移 |
| INT32 | SM S1I32F0，安全 abs 含 2^31 | 0 | 0，旁路浮点检测 |

C 从 S4 raw32 读取，独立于组 scale 链；使用固定 M32 物理端口。非零 FP32 实际指数 e_c=A_raw_c-z_c∈[-149,127]。零/特殊源旁带屏蔽，不能让 clz(0)产生普通指数；组/C 字段同拍注册。规范化逻辑上等价于 S1I1F29/F31，但本级没有这样的已左移数据出口。

## 7. S6：实际指数 MAX 与一次双向幅值移位

只对有限非零源构造 e_i=A_raw_i-z_i 并取 signed `E_max=max(e_i)`；全零使用 safe E_max=0 和 numeric_active=false。默认 W=M_global=global_signed_align_width-1=39。

```text
x_i = m_raw_i << (W-M_i)             // 静态低补：组9、C7
d_i = E_max-e_i                     // 完整unsigned数学差值
net_i = z_i-d_i = A_raw_i-E_max      // 宽signed，正左、负右
if net_i >= 0: aligned_mag_i = x_i << net_i
else:          aligned_mag_i = x_i >> (-net_i)
lambda_common = E_max-(W-1)
```

e 保守范围[-307,288]（signed10），d=0..595（unsigned10）。net 及减法临时量使用 signed11；更改窗口/能力集后重新推导。由 E_max≥e_i 得 net_i≤z_i，左移无有效位溢出。按完整 net 生成方向/abs 移位量；右移量≥W 强制输出零；正向计数必须≤z_i。默认保留完整 d/net 用于 trace，再对净移位量处理窗口；不能直接截取差值低位。d≥W 直接置零在规格化参考中同样成立，但须与精确 net 的记录口径分开。`A_raw-E_max`可作为实际硬件的单次减法，z-d 为等价语义与 trace。

| 路径 | S6 TC 格式 | 公共坐标 | 默认宽度 |
| --- | --- | --- | --- |
| 所有浮点 | S1I1F38 | alpha=E_max | W40，G+1 叶 |
| INT8+INT32 | S1I32F7 | alpha=0，结构低零 | W40，G+1 叶 |

右移为 unsigned 幅值 RTZ，随后恢复补码；左移为精确变换。整数先精确去掉组 F12 结构零、与 C 统一补 7 低零，旁路浮点 MAX/双向移位。

## 8. S7：一次求和，保留全部增长位

| FP16 基准 K | 组数 G / 含 C 项数 N | 树深 L(N) | SOP 总宽 | 浮点 TC 格式 | INT8 TC 格式 |
| --- | --- | --- | --- | --- | --- |
| 4 | 1 / 2 | 1 | 41 | S1I2F38 | S1I33F7 |
| 8 | 2 / 3 | 2 | 42 | S1I3F38 | S1I34F7 |
| 16 | 4 / 5 | 3 | 43 | S1I4F38 | S1I35F7 |

一般式 `W_sum=W_align+ceil(log2(N))`。S7 保留 S6 的 A_common（默认 signed 10 位）和 F，不因加法自动改变参考指数。若改用 S7 容器最高幅值位作为 anchor，其值必须增加 L(N)；不得一边加宽一边仍把最高物理位权重当作原值。最小 K 和非二次幂扇入均按自然树深生成。

## 9. S8：FP32 编码或 INT32 回绕

浮点对 S7 的安全绝对值找最高非零 coefficient 位 k，`E_out=A_common-(M_global-1)+k`。

默认 S7 非零结果的安全指数包络为 [-345,291]；RNE 进位按上界再加一检查，signed10 仍足够。此包络由 e_min-(M_global-1) 与 e_max+ceil(log2(G+1)) 推导，各中间加减独立检查宽度。

规范化后的逻辑幅值容器为 I1F23（正常 h=1、非正规 h=0），按 RNE 形成输出；最终 32 位是 **S1/E8/F23 浮点编码，不再是 S1IxFx 定点总线**。整数精确删除结构低零后，输出 R mod 2^32，按 TC S1I31F0 解释；范围溢出只写验证 trace。本级同步输出当前结果 datatype、valid、last。

## 10. 与 C 比较的可核对例子

FP16 组内四个 1×1、C=1：S5 组 m_raw=2^28、F_raw=26、A_raw=3、z=1，e=2；C 的 m_raw=2^31、A_raw=0、z=0。S6 E_max=2；组 d=0、net=1，静态补 9 零后左移 1 得到 2^38；C d=2、net=-2，静态补 7 零后右移 2 得到 2^36。共同 lambda=-36，总值为 5。

最小正非正规 C：S5 m_raw=2^8、A_raw=-126、z=23、e=-149；若其他源都为零，S6 E_max=-149、d=0、net=23，静态补 7 零后左移 23 得到 2^38，值仍为 2^-149。

**推导更正：** 不得把 d 截取低位后取模；例如 d=64 截成 6 位 0，会错误地产生左移。d≥W 时，先完整规格化的 W 位参考必为零，因此直接输出零或先将 d 饱和到 W 再代入 z-d，在数据结果上均等价；后者的 net 仅是饱和控制值，不能当作精确数学 net 写入 trace。默认合同保留完整 d/net 语义，再生成有限宽控制。

## 11. 参数约束与 trace

最小 unsigned/signed 宽度由合法范围推导：`uwidth(hi)=max(1,ceil(log2(hi+1)))`；`swidth(lo,hi)` 为满足 `-2^(w-1)≤lo` 且 `hi≤2^(w-1)-1` 的最小 w。常量指数可在生成时移除，但 trace 保留语义值。共用宽度取当前能力集所需宽度的最大值；临时加减法按其**中间**范围推导，截宽必须有证明。

每级 trace 至少记录 request/datatype、valid/last、数值表示 SM/TC、物理宽度、F、alpha 或 r/A 的命名坐标、special/zero。r、alpha、A 与 lambda 不能都笼统叫 exp。C S1–S4 只显示 raw32，S5 才出现分类和解包坐标；S6 全部叶与 S7 总和可按同一 lambda 直接复算。
