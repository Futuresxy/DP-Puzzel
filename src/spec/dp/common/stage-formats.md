> 功能：列出每级数值出口的定点格式与指数范围；范围：S1–S8、同格式 A/B、C 的 S5 解包、anchor 与 SOP；版本：v1.5.4；修改时间：2026-11-05 14:16:26 +08:00；对应代码：[CModel lib/detail.hpp](../../../cmodel/lib/detail.hpp)；分组主方案手写 RTL：[dp_top.v](../../../verilog/top/dp_top.v)；Chisel 尚未实现。

# 每级 anchor、SOP 与 SxIxFx

状态：本表按 [位宽推导](numeric-layout.md) 展开各接口及默认数值例。CModel、RTL 与后续 Chisel 使用同一组公式。按事务 datatype 选择解释，同一物理端口可携带不同的小数点。

## 1. 记号和数值坐标

- `S1IiFf` 的一位 S **不包含在 I 内**，总数值位宽为 `1+i+f`。`SM` 指独立符号加无符号幅值，`TC` 指二补码；两者不能直接按位互换。
- `S0IiFf` 为无符号 coefficient。SM 的 S 可来自独立符号线；表内位宽不包括指数、valid、datatype 或特殊值旁带，也不包括固定 E/M/S 容器中闲置的零。
- 对 TC 整数 coefficient q，实际值为 `q × 2^(alpha-F)`；对 SM 为 `(-1)^negative × magnitude × 2^(alpha-F)`。SxIxFx 描述 coefficient 的定点解释，alpha 描述额外的二进制指数。
- `r` 是基本组内有限非零乘积的最大**有效偏置指数和**；`alpha` 是去偏置并融合 scale 指数后的参考指数；`A` 是幅值容器最高物理位的权重，即 `A=alpha-F+(M-1)`。只有相同坐标的指数才能直接比较。
- S1 尚无乘积，S2 尚无 SOP，不能把它们的单元素或单乘积字段标成组 SOP。S3 只有 E pair 已是局部 SOP；S4 才产生每 lane 一个 SOP。

`K` 以 FP16 并行度为基准，`G=K/4`，`N=G+1` 包含 C，`L(n)=ceil(log2(n))` 且 `L(1)=0`。记 `P=LOCAL_W-2`、`F_g=GLOBAL_W-2`，记号 `F(P+1)` 表示 F 字段有 P+1 位。T 为 TF32，H 为 FP16/BF16，Q 为 MXFP8 E4M3/E5M2 和 MXFP6 E3M2/E2M3，E 为 MXFP4/NVFP4/HiF4。

局部补码叶宽 `W_leaf=LOCAL_W+1`、lane 宽 `W_lane=W_leaf+L(4)`、组宽 `W_group=W_lane+L(2)`，幅值宽 `M_group=W_group-1`、`M_global=GLOBAL_W-1`。默认 `LOCAL_W=28`、`GLOBAL_W=40`，故 P=26、F_g=38、W_leaf/W_lane/W_group=29/31/32、M_group/M_global=31/39。

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

E/M/S 的**物理接口**仍为每原子块 E10/M16/S4，按 [解包](../lane/unpack.md) 切片；不能把 E10 当成一条十位指数。Q 的有限有效指数范围：E5M2 为 1..30，E4M3 为 9..23，E3M2 为 13..19，E2M3 为 15..17。零/特殊数占位不参与有限非零 MAX。

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

| 模式 | 有效叶 / lane | S3 共享幅值移位器输入/输出 | S3 树叶（TC，W_leaf） | alpha |
| --- | ---: | --- | --- | --- |
| T | 1 | S0I2F(P) | S1I2F(P) | r-254 |
| FP16 | 2 | S0I2F(P) | S1I2F(P) | r-30 |
| BF16 | 2 | S0I2F(P) | S1I2F(P) | r-254 |
| Q | 4 | S0I2F(P) | S1I2F(P) | r-30，尚未施加块 scale |
| MXFP4/NVFP4 | 4 个 pair | S0I7F(P-5) | S1I7F(P-5) | 0，尚未施加块 scale |
| HiF4 | 4 个 pair | S0I5F(P-3) | S1I5F(P-3) | r，尚未施加块 scale |
| INT8 | 4 | S0I15F(P-13) | S1I15F(P-13) | 0，F 全部为结构低零 |

T/H/Q 乘积按 `P-F_product` 低补零后对幅值 RTZ，之后恢复符号。E pair 的两个输入在补码 W9 中为 S1I6F2（MX/NV）或 S1I4F4（HiF4），加一位整数位得到 W10。再补两位 guard 和 `W_leaf-12` 位结构低零。HiF4 的 0/1/2 位移只消耗预置低零。INT8 的 W16 有效积补 `W_leaf-16` 个低零。S3 保留 S2 公共 r，旁带独立传递。

## 5. S4：每 lane 一个 SOP

| 模式 | 自然 SOP 宽度 / F | 到 W_lane 的低零数 | S4 出口（TC） | 默认 28/40 |
| --- | --- | ---: | --- | --- |
| T | W_leaf / P | 2 | S1I2F(P+2) | S1I2F28 |
| FP16/BF16 | W_leaf+1 / P | 1 | S1I3F(P+1) | S1I3F27 |
| Q | W_leaf+2 / P | 0 | S1I4F(P) | S1I4F26 |
| MXFP4/NVFP4 | 紧凑 W14 / F4 | W_lane-14 | S1I9F(P-5) | S1I9F21 |
| HiF4 | 紧凑 W14 / F6 | W_lane-14 | S1I7F(P-3) | S1I7F23 |
| INT8 | W18 / F0 | W_lane-18 | S1I17F(P-13) | S1I17F13 |

E/INT8 的低零已在 S3 落位，S4 不重复追加。四叶树物理输出自然增宽两位。T/H 仅使用 1/2 个非零槽，因此可分别低补 2/1 位而不丢高位。S4 沿用本组 r/alpha。

## 6. S5：scale 后原始 SOP 与 LZD 计数

两 lane 的 S4 TC 输出为组树输入，组树输出将每种格式的 I 增加一位，F 保持。先取组和的独立符号与幅值。只有 NVFP4/HiF4 取紧凑组和的 14 位幅值参与乘法。两侧 scale 各为 S0I1F3，系数积为 8 位 S0I2F6。

| 模式 | 紧凑组和（TC） | 乘法器幅值输入 | W22 无符号乘积 | M_group 幅值落位 |
| --- | --- | --- | --- | --- |
| NVFP4 | S1I10F4 | S0I10F4 | S0I12F10 | 低补 M_group−22 位，S0I12F(P-7) |
| HiF4 | S1I8F6 | S0I8F6 | S0I10F12 | 低补 M_group−22 位，S0I10F(P-5) |

默认从 W32 组槽去掉 17 个低零，W22 幅值乘积补 9 个低零。其余格式保留原组和的完整幅值。LZD 读默认 M31 的幅值并仅输出 z，符号独立传到 S6。

| 模式 | S5 SM 出口 | 默认格式 | alpha_raw 范围 | A_raw 范围 | e=A_raw-z 默认保守范围 |
| --- | --- | --- | --- | --- | --- |
| T | S1I3F(P+2) | S1I3F28 | [-252,254] | [-250,256] | [-280,256] |
| FP16 | S1I4F(P+1) | S1I4F27 | [-28,30] | [-25,33] | [-55,33] |
| BF16 | S1I4F(P+1) | S1I4F27 | [-252,254] | [-249,257] | [-279,257] |
| Q | S1I5F(P) | S1I5F26 | [-282,284] | [-278,288] | [-308,288] |
| MXFP4 | S1I10F(P-5) | S1I10F21 | [-254,254] | [-245,263] | [-275,263] |
| NVFP4 | S1I12F(P-7) | S1I12F19 | [-12,16] | [-1,27] | [-31,27] |
| HiF4 | S1I10F(P-5) | S1I10F21 | [-96,32] | [-87,41] | [-117,41] |
| INT8 | S1I18F(P-13) | S1I18F13 | 0 | 浮点字段置 0 | 不参与 |

`alpha_raw=r-bias_a-bias_b+(scale_E_a+scale_E_b-254)`，无 scale 时括号为 0。组 token 注册 `m_raw,negative,A_raw,z,zero/special,ctrl,valid/last`。默认 A_raw signed10、z unsigned5，非零 z≤30。以 `A_raw=alpha_raw+(M_group-1)-F_raw` 表示组幅值最高位权重，故 `value=(-1)^negative × m_raw × 2^(A_raw-(M_group-1))`。增加 LOCAL_W 同时增加 M_group 和 F_raw，A_raw 仍用同一坐标。

| C 类型 | S5 原幅值出口 | A_raw_c | z_c |
| --- | --- | --- | --- |
| FP32 | 自然 M24={h,F23}低补 8 零→SM S1I1F31，M32 | (raw_e==0?1:raw_e)-127，[-126,127] | 正规 0；非正规非零 clz24=1..23；不动态左移 |
| INT32 | SM S1I32F0，安全 abs 含 2^31 | 0 | 0，旁路浮点检测 |

C 从 S4 raw32 读取，独立于组 scale 链；使用固定 M32 物理端口。非零 FP32 实际指数 e_c=A_raw_c-z_c∈[-149,127]。零/特殊源旁带屏蔽，不能让 clz(0)产生普通指数；组/C 字段同拍注册。C 与组的动态规格化都在 S6 的同一次移位中完成。

## 7. S6：实际指数 MAX 与一次双向幅值移位

只对有限非零源构造 e_i=A_raw_i-z_i 并取 signed `E_max=max(e_i)`；全零使用 safe E_max=0 和 numeric_active=false。默认 W=M_global=global_signed_align_width-1=39。

```text
x_i = m_raw_i << (W-M_i)             // 默认静态低补：组8、C7
d_i = E_max-e_i                     // 完整unsigned数学差值
net_i = z_i-d_i = A_raw_i-E_max      // 宽signed，正左、负右
if net_i >= 0: aligned_mag_i = x_i << net_i
else:          aligned_mag_i = x_i >> (-net_i)
lambda_common = E_max-(W-1)
```

e 默认保守范围 [-308,288]（signed10），d=0..596（unsigned10）。net 及减法临时量使用 signed11；更改窗口/能力集后重新推导。由 E_max≥e_i 得 net_i≤z_i，左移无有效位溢出。按完整 net 生成方向/abs 移位量；右移量≥W 强制输出零；正向计数必须≤z_i。默认保留完整 d/net 用于 trace，再对净移位量处理窗口；不能直接截取差值低位。d≥W 直接置零在规格化参考中同样成立，但须与精确 net 的记录口径分开。`A_raw-E_max`可作为实际硬件的单次减法，z-d 为等价语义与 trace。

| 路径 | S6 幅值输入 | S6 TC 输出 | 默认输出 |
| --- | --- | --- | --- |
| 所有浮点 | S0I(I_raw)F(F_raw+W-M_i) | S1I1F(F_g)，alpha=E_max | S1I1F38 |
| INT8+INT32 | S0I32F(GLOBAL_W-33)，移位旁路 | S1I32F(GLOBAL_W-33)，alpha=0 | S1I32F7 |

右移为 unsigned 幅值 RTZ，随后恢复补码；左移为精确变换。整数先精确去掉组 `P-13` 个结构零、与 C 统一补 `GLOBAL_W-33` 个低零，旁路浮点 MAX/双向移位。

## 8. S7：一次求和，保留全部增长位

| FP16 基准 K | 组数 G / 含 C 项数 N | 树深 L(N) | SOP 总宽 | 浮点 TC 格式 | INT8 TC 格式 |
| --- | --- | --- | --- | --- | --- |
| 4 | 1 / 2 | 1 | 41 | S1I2F38 | S1I33F7 |
| 8 | 2 / 3 | 2 | 42 | S1I3F38 | S1I34F7 |
| 16 | 4 / 5 | 3 | 43 | S1I4F38 | S1I35F7 |

一般式 `W_sum=GLOBAL_W+L(N)`，浮点为 S1I(1+L(N))F(F_g)，整数为 S1I(32+L(N))F(GLOBAL_W-33)。S7 保留 S6 的 A_common（默认 signed 10 位）和 F，不因加法自动改变参考指数。若改用 S7 容器最高幅值位作为 anchor，其值必须增加 L(N)；不得一边加宽一边仍把最高物理位权重当作原值。最小 K 和非二次幂扇入均按自然树深生成。

## 9. S8：FP32 编码或 INT32 回绕

浮点对 S7 的安全绝对值找最高非零 coefficient 位 k，`E_out=A_common-(M_global-1)+k`。

默认 S7 非零结果的安全指数包络为 [-346,291]；RNE 进位按上界再加一检查，signed10 仍足够。此包络由 e_min-(M_global-1) 与 e_max+ceil(log2(G+1)) 推导，各中间加减独立检查宽度。

规范化后的逻辑幅值容器为 I1F23（正常 h=1、非正规 h=0），按 RNE 形成输出；最终 32 位是 **S1/E8/F23 浮点编码，不再是 S1IxFx 定点总线**。整数精确删除结构低零后，输出 R mod 2^32，按 TC S1I31F0 解释；范围溢出只写验证 trace。本级同步输出当前结果 datatype、valid、last。

## 10. 与 C 比较的可核对例子

FP16 组内四个 1×1、C=1：S5 组 m_raw=2^29、F_raw=27、A_raw=3、z=1，e=2；C 的 m_raw=2^31、A_raw=0、z=0。S6 E_max=2；组 d=0、net=1，静态补 8 零后左移 1 得到 2^38；C d=2、net=-2，静态补 7 零后右移 2 得到 2^36。共同 lambda=-36，总值为 5。

NVFP4 默认幅值积 S0I12F10 低补 9 位进入 S5，再低补 8 位进入 S6 幅值槽。此时幅值在原 alpha 坐标为 S0I12F27。若净移位为 0，位模式原样输出，在公共 E_max 坐标解释为 S0I1F38，再恢复符号。17 个补零位是静态落位。

最小正非正规 C：S5 m_raw=2^8、A_raw=-126、z=23、e=-149；若其他源都为零，S6 E_max=-149、d=0、net=23，静态补 7 零后左移 23 得到 2^38，值仍为 2^-149。

**推导更正：** 不得把 d 截取低位后取模；例如 d=64 截成 6 位 0，会错误地产生左移。d≥W 时，先完整规格化的 W 位参考必为零，因此直接输出零或先将 d 饱和到 W 再代入 z-d，在数据结果上均等价；后者的 net 仅是饱和控制值，不能当作精确数学 net 写入 trace。默认合同保留完整 d/net 语义，再生成有限宽控制。

## 11. 参数约束与 trace

最小 unsigned/signed 宽度由合法范围推导：`uwidth(hi)=max(1,ceil(log2(hi+1)))`；`swidth(lo,hi)` 为满足 `-2^(w-1)≤lo` 且 `hi≤2^(w-1)-1` 的最小 w。常量指数可在生成时移除，但 trace 保留语义值。共用宽度取当前能力集所需宽度的最大值；临时加减法按其**中间**范围推导，截宽必须有证明。

每级 trace 至少记录 request/datatype、valid/last、数值表示 SM/TC、物理宽度、F、alpha 或 r/A 的命名坐标、special/zero。r、alpha、A 与 lambda 不能都笼统叫 exp。C S1–S4 只显示 raw32，S5 才出现分类和解包坐标；S6 全部叶与 S7 总和可按同一 lambda 直接复算。
