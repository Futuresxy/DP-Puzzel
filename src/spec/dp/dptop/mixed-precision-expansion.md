> 功能：定义三种混合DP面积优化、参与屏蔽与carry-save扩展；范围：混合DP专用前端及扩展合同；版本：v1.9.1；修改时间：2026-11-09 23:57:09 +0800；对应代码：src/cmodel/lib/top/mixed.cpp、src/verilog/top/common/dp_top_mixed.v、dp_mixed_global_align.v及三个固定顶层；本版CModel/冻结RTL验证已通过，见test/results/mixed-{cmodel,rtl}-v1.9.md；新PPA独立验收。

# 三种混合 DP：v1.9 确认合同

本轮已授权先CModel、再RTL、冻结验证、同工况DC和真实负载功耗。基础dp_top继续采用[v1.8](dp-top-v1.8.md)，单独修复综合电气违例。三个混合顶层及独立Q32E64迁移本版；Q32E64的装配合同见[四组低精度DP](low-precision-tops.md)。独立E64、dp_top_e兼容入口及冻结SV保留原设计，使用显式静态版本开关隔离。旧回执和PPA保留作对照，不代表新合同已验收。

v1.8 → v1.9：~~扩展先CPA求和后再与基础结果相加~~ → 全部在carry-save状态合并、两行MUX、唯一最终CPA；E S3融合e2、LZD22，QE保留Q对齐且E旁路；共同输出A_raw/compare_exp。

## 1. 三种配比与相对基础的修改

配比为H:Q:E原生MAC/cycle容量；T固定8，INT8固定K32。默认LOCAL_W=28/GLOBAL_W=40，L8/II=1。

|入口|容量|基础部分|新增部分|扩展参与|S7宽度|
|---|---|---|---|---|---|
|dp_top_t8h16q32e96|T8H16Q32E96，1:2:6|4个v1.8全精度group|2个E16|MXFP4/NVFP4/HiF4|S43|
|dp_top_t8h16q32e128|T8H16Q32E128，1:2:8|同上|4个E16|三种E|S44|
|dp_top_t8h16q64e128_opt|T8H16Q64E128，1:4:8|同上|4个Q8E16|四种Q及三种E|S44|

相对baseline，不改变基础T/H/Q/E/INT能力；新增吞吐由空间复制专用group取得，不做时间复用。基础组也要显式选用v1.8，不能仅迁移新增组。物理总面积可能增加，优化目标是降低新增容量的面积/功耗代价，不承诺比基础DP更小。

## 2. 专用前端

[E lane](../lane/dp_lane_E.md)：S1专用解包；S2八个4×4乘法和四个S10 pair；S3两层树S12、局部e2融合后保存S14；S4组和S15/abs U14；S5 scale U14×U8及LZD22。没有T/H/Q/INT解包、宽乘积拼接、跨lane MAX或宽右移器。

[QE lane](../lane/dp_lane_qe.md)：仅Q/E解包；Q U5指数加法得到U6，不保留T/H的8位元素指数加法。S2乘法与Q公共MAX，S3 Q U28对齐或E窄pair旁路，S4共享树与E局部e2融合。QE不将E移位重新送入Q宽移位器。E专用S3已完成树，QE树在S4，故两者e2消费级不同但均不离开lane。

[E group](../group/dp_group_E.md)在S4保存U14幅值；S5统一U22容器（MX幅值低补8零，NV/HiF乘积22位），LZD22和低补M-22零输出M位幅值。非零LZD不因低补零而改变，零通过active处理。

[QE group](../group/dp_group_qe.md)仍S5完成两个S31求和S32/abs及scale，使用共享LZD31。三类组均采用无偏scale S8、S2指数和S9、S3 A_raw S10、S5 compare_exp S10；不重复减scale bias。

## 3. 输入分发与 scale 布局

令 B=4、X 为扩展组数、G=B+X。A/B 都按 64 位一组，低位先放原四组，高位放扩展组：

```text
group g: in_a[g*64 +: 64], in_b[g*64 +: 64]
lane l within group: group_data[l*32 +: 32], l=0/1
base groups: g=0..3
extension groups: g=4..G-1
```

| 顶层 | G | A/B 各宽 | 每侧 scale | 每侧 HiF4 e1 | 每侧 HiF4 e2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| e96 | 6 | 384 | 48 | 24 | 12 |
| e128 | 8 | 512 | 64 | 32 | 16 |
| Q64e128 | 8 | 512 | 64 | 32 | 16 |

scale 每组 8 位、e1 每组 4 位（每四个 E 元素一位）、e2 每组 2 位（每 E8 lane 一位）。其余端口方向、datatype、A/B/C 原子接收、last、无输出背压沿用 [接口](interface.md)。C 为单个 raw32。A/B 同格式；T/H 搭配 SC_NONE/FP32 C，Q/E 使用其规定 scale/FP32 C，INT8 使用 SC_NONE/INT32 C。非法类型组合拒绝，不因扩展能力改变合法性。

非扩展模式只读低 256 位；高位 payload、scale 和 HiF 元数据即使翻转也不得影响该请求。扩展模式的逻辑向量连续排列，E 的前 64 项在基础支，其余在扩展支；Q64 的前 32 项在基础支，其余在扩展支。

量化块和 group 不是同一概念。输入适配层按逻辑 scale 块将同一 scale 广播至对应组，两侧分别处理：

| 精度 | 每组元素数 | 每 scale 块元素数 | group g 使用的逻辑 scale 编号 |
| --- | ---: | ---: | --- |
| Q | 8 | 32 | floor(g/4) |
| MXFP4 | 16 | 32 | floor(g/2) |
| NVFP4 | 16 | 16 | g |
| HiF4 | 16 | 64 | floor(g/4) |

例如 E96 的 HiF4 scale 广播为 `[s0,s0,s0,s0,s1,s1]`，尾部 32 项使用第二个块的 scale；不能改成 E16 量化或重新量化。外部参考数据的物理 scale 槽可能稀疏，必须按来源元数据解码为上述逻辑顺序，不能直接复制其槽号当作本项目组号。

## 4. 参与、非零和有效的区别

扩展参与表随请求决定：

| 顶层 | T/H | Q | E | INT8 |
| --- | --- | --- | --- | --- |
| e96/e128 的扩展支 | 关闭 | 关闭 | 开启 | 关闭 |
| Q64e128 的扩展支 | 关闭 | 开启 | 开启 | 关闭 |

基础支始终计算合法请求。定义 `participate[g]` 为该请求在此组有逻辑元素；`numeric_active[g]` 为参与且有限非零。后者只决定浮点 MAX 和数值移位，不能用于屏蔽 NaN/Inf 或负零。

输入只在 `request_fire & extension_supports_datatype` 时写入扩展 group，气泡 valid 继续每拍传递。类型和参与标志与请求一起保存到 r5/r6/r7；不能用当前输入 datatype 关闭所有阶段，否则“前拍 E、后拍 H”会丢失仍在途的 E 计算。复位为同步低有效 `rst_n`，取消全部在途 valid，数据寄存无需复位。

S5 必须断言参与组的 out_valid 与对应请求对齐，非参与组无本笔有效输出；不能把某个应参与组的意外无效当成正常旁路。非参与组可能仍保留上一次 NaN、负号或很大指数，必须在进入后端时逐类屏蔽：

| 后端用途 | 非参与组的处理 |
| --- | --- |
| MAX | `has_value=0`；无资格竞争最大指数 |
| 移位及加法 | 输入幅值/移位控制隔离，叶子恒为 0 |
| special | 对 OR 归约贡献 0；不触发 NaN/Inf/invalid |
| 全负零条件 | 对 AND 归约贡献 1，不把它视为正零元素 |

负零按参与的原始叶子处理：每路贡献为 `!participate || (negative && aligned_magnitude==0)`，对基础组、扩展组和 C 取 AND；这是一条数学布尔表达式，实际 RTL 按项目规则编码。总和为零时才使用该摘要。非零正负项抵消不能被错误标成全负零。

现有 `dp_global_align` 只有整次使能，special/negative_zero 归约会读取所有槽；**不能直接多接几个零幅值 token 就结束**。新后端需要显式源参与掩码，或等价的完整边界适配；若扩展公共模块接口，既有 top 接全参与并回归。尤其不能用统一 `sign=0, magnitude=0` 代表不参与，这会破坏原负零结果。

## 5. S5 token 与 S6 全局对齐

默认公共输出为sign1、magnitude U31、A_raw S10、compare_exp S10、special及valid。z只作兼容观察，后端不重复执行A_raw-z。数值不变量：

```text
value = (-1)^sign * magnitude * 2^(A_raw-(M-1))
compare_exp = A_raw - LZD_M(magnitude)   // 有限非零group
```

E内部LZD22沿用最终M位的A_raw，MX在U22容器低补8零，最终再补M-22零。零/特殊compare_exp置安全值且numeric_active=0；special仍按participate独立归约。

C解包沿基础v1.8：FP32非正规保留0.xxx，有效指数-126，不做C LZD；零/特殊C不参与普通MAX。INT32 C取完整幅值。C只加一次。

基础MAX包含四group+C，扩展MAX包含2/4group，分别携带has_value，按参与条件合并为唯一Emax；不能用指数0替代无效候选。两支同时在这个Emax下对每个源各做一次RTZ对齐，不先在各支自己的Emax下求和再合并。

S6 group U31低补8零至U39，C M32低补7零。净移位net=A_raw-Emax为S11，正值左移，负值幅值右移，超范围不能取模。恢复符号产生每路S40。扩展源静态为浮点，删除其INT重排/直通选择；基础与C保留INT旁路。整体7/9路，包括唯一C。

## 6. S7 carry-save分支及S8

所有叶子先符号扩展到W=GLOBAL_W+ceil(log2(G+1))：E96 W43，两个128变体W44。carry行定义为已经左移、包含位权，最终不再左移。

```text
base4 → CSA4:2 → (两行,C) CSA3:2 → base_s,base_c
X=2: (base_s,base_c,extra0,extra1) → CSA4:2 → merged_s,merged_c
X=4: extra4 → CSA4:2 → extra_s,extra_c
     (base_s,base_c,extra_s,extra_c) → CSA4:2 → merged_s,merged_c
按本笔格式同时选择两行(base或merged) → 唯一CPA → S43/S44
```

扩展网络不含预加CPA；MUX为两个W位选择器，不是把两行误作一行。关闭扩展时选基础两行，仍经过公共最终CPA；高精度并不保证物理时序与baseline完全相同。

INT仅基础四组+C，S6整数是S1I32F7；S7为S1I35F7或S1I36F7，最终固定取[38:7]，丢掉低7个补零和高位溢出，保持INT32回绕而非饱和。浮点S7为S1I4F38或S1I5F38，完整43/44位送abs/LZD/规格化/RNE；LZD计数6位，Emax坐标不变。

## 7. 面积和功耗修改依据

|修改|目的|不能据此宣称|
|---|---|---|
|E/QE专用解包、静态删除T/H/INT|减少格式MUX、宽字段及无关分类|现有专用解包已实现的收益不能重复计算|
|E S2先pair，S3窄树|S2只存4×10而非8×9位|逻辑寄存位差不等于映射面积|
|E S3消费e2|不向S4传移位控制，S4更轻|S3寄存从12增为14，净收益需测|
|E S4窄组和/abs|避免S32组加法及S5串联组和|QE受Q窗口约束不能照抄窄组树|
|E LZD22，公共U31接口|降低显式检测输入宽度、保持复用|旧LZD常量可能已被DC裁剪|
|QE E绕过Q对齐、分段精度门控|减少E时无效指数/宽数据翻转|共享宽树仍存在，不等于独立E功耗|
|扩展participate逐级保持/隔离|T/H/INT时停止新增数据更新和无效组合活动|仅末端MUX不能降低前端翻转|
|S7 carry-save合并/唯一CPA|减少串联进位传播，降低时序修复压力|CSA不保证比所有CPA方案面积更低|

复用计算模块及当前时钟门控流程；不手写组合门控时钟。失活group对MAX、special、负零的贡献分别屏蔽，单纯把幅值清零不充分。历史所有功耗及其依赖保留；不能用门控覆盖率代替真实负载功耗。

## 8. 潜在优化与验收

尚未纳入本版：S1提前XOR只保存乘积符号（核对所有消费者/负零）；QE更细分寄存使能及操作数隔离；基于实际范围缩小Q delta控制而非截断取模；E小系数专用乘法；QE独立窄E树；压缩器平衡和MUX位置优化。均需独立实验，收益和代价不能预填。当前不减LOCAL/GLOBAL精度、不增加流水或时间复用。

优先实测解包/寄存、Q对齐、共享树、扩展S6/S7各自面积与Q/E活动功耗，再选热点。QE独立E树可能降功耗却增面积；额外隔离MUX也可能恶化时序。

后续先CModel，再RTL/冻结Verilator，再同库N12 TT/0.7V/85°C、1GHz门控及电气检查；功耗使用各自经过验证的网表、新生成VCS原生SAIF和Power Compiler，在兼容模式下比较BF16、MXFP8 E4M3、MXFP4；E64复用未改设计的合法综合输入并重新采样。验证包括E96/E128三格式、Q64四格式全量数据；T/H/INT及不扩展Q对照基础v1.8；U22与M位LZD非零等价/零差异；scale/e1/e2边界、抵消、负零、Inf/NaN；失活扩展毒化；逐拍换型/气泡/复位；CSA有符号边界和carry位权；N7/N9及参数窗口；C只计一次。

数据来源沿用test/data中既有E96/E128/Q64向量与exact参考，来源分别为fp48、fp416、low16，不重定义量化块。数学golden不随硬件改动；同时报告RTL/CModel一致性及数学ULP。任何共享源码修改都需明确旧E/QE/低精度顶层是否隔离或重验。当前三种新架构未形成新PPA；旧约66%面积增长是旧版本证据，不作为本版预测或硬性承诺。
