> 功能：讨论 E16 专用基本组及 E-only DP 接入；范围：两 lane MAX、S5 组和/scale/LZD、S6–S8 复用与 PPA 验收；版本：v1.5.2；修改时间：2026-11-05 13:33:21 +08:00；对应代码：专用实现尚未建立；推导基线为 [dp_group.v](../../verilog/group/dp_group.v)、[dp_scale_multiply.v](../../verilog/arithmetic/dp_scale_multiply.v)、[dp_top.v](../../verilog/top/dp_top.v)、[CModel group.cpp](../../cmodel/lib/group.cpp)。

# E 类专用 group 讨论稿

状态：候选方案，待用户确认；没有替换现有多精度实现，没有测得专用面积、时序或功耗。配套 lane 见 [dp_lane_E](dp_lane_E.md)。优化重点是 S1–S5 的计算与寄存器宽度，同时复用当前 FP32 后端，保持一笔 scaled_dot(A,B)+C、L8/II=1、无跨请求累加状态。

## 1. 组织、流水与顶层适配

基本组为两个 E8 lane，即 E16；G=1/2/4 对应 E16/E32/E64，默认 G=4。对照现有配置时 `K_E`=4×`K_FP16`=16G。A/B 各需 4×`K_E` 个原始数据位，默认均为 256 位。量化块 scale 与 HiF4 元数据继续按 [输入布局](layout-and-scales.md) 广播，不能把 MX 的 32 元素 scale 块误改成每组独立 16 元素块。

| 边界 | 主要计算 | E 专用调整 |
| --- | --- | --- |
| S1 | E 解包、scale 解包 | 删除 T/H/Q/INT8 解包和元素特殊值分支 |
| S2 | 8×4×4/lane、两 lane MAX、scale 系数/指数和 | lane exponent 缩为 2 位；保留 scale 4×4→8 |
| S3 | pair/局部精确对齐 | 12 位 TC 叶子，移位只取 0/1/2 |
| S4 | lane 平衡树 | 14 位 TC 输出 |
| S5 | 两 lane 求和、abs、scale、LZD；C 解包 | 15 位组 TC、14×8 无符号乘法、建议 M22 token |
| S6 | 各组与 C 的实际指数 MAX、一次双向移位 | 保留默认 `GLOBAL_W`=40，适配组 token 宽度 |
| S7 | G+1 路 TC 树 | 保留参数化树 |
| S8 | FP32 规格化与 RNE | 保留 FP32，删除 INT32 回绕/模式 mux |

主体优化在 lane/group，但完整 E-only DP 仍要少量顶层适配：替换 group 实例、声明 E-only 合法模式、调整源幅值宽度/静态补零及移除整数控制。当前 `dp_top` 静态实例化通用 `dp_group`，不能只修改两个文件名就获得正确专用顶层。建议后续单独建立轻量 `dp_top_E`，复用既有 S6/S7/S8 算术模块；原 `dp_top` 保留作比较基线。

## 2. 组内 MAX 与 S5 求和

MX/NV 的组内元素 anchor 恒为 0。HiF4 对两个 lane 的 `p_lane`=e2A+e2B 做 2-bit unsigned MAX，`active` 采用 [lane 定义](dp_lane_E.md) 的非零乘积候选，S2 寄存返回值。无需 8 输入宽 MAX，也无需逐产品保存宽指数。

S4 两个 14 位 TC lane SOP 以相同 group anchor 为坐标相加，S5 得到 15 位 TC 组和。先提取符号与幅值，再应用 scale。abs 应在足够宽的中间量计算并验证范围，合法有限 E 输入的幅值可装入 14 位。零符号仍取原来的 `all_negative` 规则；乘零 scale 时不能丢失负号规则。

| 信号 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | --- | --- | --- | --- |
| S5 scale 前组和 | MXFP4/NVFP4 | TC | 1 | 10 | 4 | 15 |
| S5 scale 前组和 | HiF4 | TC | 1 | 8 | 6 | 15 |
| 组和绝对值/scale A 输入 | MXFP4/NVFP4 | unsigned | 0 | 10 | 4 | 14 |
| 组和绝对值/scale A 输入 | HiF4 | unsigned | 0 | 8 | 6 | 14 |
| 两侧 scale 系数积/scale B 输入 | NVFP4/HiF4 | unsigned | 0 | 2 | 6 | 8 |
| scale 输出 | NVFP4 | unsigned | 0 | 12 | 10 | 22 |
| scale 输出 | HiF4 | unsigned | 0 | 10 | 12 | 22 |

14 位幅值的保守界限是 NVFP4：16×12²×4=9216；HiF4：16×14²×4=12544，均小于 2^14。保护零和右移已计入该界限，不能再将结果扩回通用 32 位后才求 abs。

## 3. scale 专用化

MXFP4 采用 E8M0，系数积恒为 1.0，只融合指数，数据旁路。NVFP4/HiF4 共用现有 14×8 unsigned scale 数据乘法器；新专用化不再把它改为更宽乘法。可以删除其他 datatype 的选择及虚拟单位 scale 记录，但三种 scale 解包及特殊值必须保留。

NV 的负 E4M3 scale 仍是非法 payload；E8M0/E6M2 的 0xff、E4M3 NaN 和零语义遵循 [scale](scale.md) 与 [特殊值](special-values.md)。元素均有限不意味着 FP32 C 或 scale 均有限。对外保持原 datatype/scale 类型组合检查；内部可压缩成少量专用控制位。

MX 请求与无效请求应对 scale 系数/数据乘法器进行 operand isolation 或有效位保持，避免旁路时仍反复切换。具体启用方式需比较隔离 mux 的面积、时序代价；不用自造门控时钟。

## 4. 推荐的 22 位幅值 token

现有默认组幅值 M31 中，NV/HiF 的 22 位乘积补 9 个低零。E 专用可以在组输出保留 22 位幅值，符号单独传递；MX 的 14 位组幅值只需补 8 个低零，以统一相同接口。

| S5 组输出 | 表示 | S | I | F | 幅值位宽 M | 形成方式 |
| --- | --- | --- | --- | --- | --- | --- |
| MXFP4 | SM | 1 | 10 | 12 | 22 | abs(group_tc) 低补 8 零 |
| NVFP4 | SM | 1 | 12 | 10 | 22 | 14×8 乘积原样输出 |
| HiF4 | SM | 1 | 10 | 12 | 22 | 14×8 乘积原样输出 |

推荐 token 包含 `magnitude`[21:0]、`negative`、`active`、已去 bias 的 `A_raw`、z[4:0] 及必要特殊值摘要。S5 不左移做规格化，仍只输出 LZD 计数。这里删的是固定零，不能宣称额外保留了新的小数精度。

`active` 可由幅值和特殊值组合派生，避免增加冗余寄存器。接入现有后端时，z 按后端 `Z_W` 零扩展，`A_raw` 按 `ANCHOR_W` 符号扩展；不能让连接时的隐式截断决定数值。

~~~text
value = (-1)^negative * m * 2^(alpha-F)
A_raw = alpha - F + (M-1)
e = A_raw - z

默认基线：m_base = m_E << 9; M_base=31; M_E=22
          F_base = F_E + 9
          A_raw_base = A_raw_E
          clz31(m_E<<9) = clz22(m_E)     // 非零输入
~~~

低端压缩不改变 LZD 计数 z；不能把 z 再减 9。零源保持 inactive，并把 z/A 设置为安全值。以同一 `A_raw` 与 z 接入 S6，实际指数、MAX 和对齐后幅值保持基线语义。

| 组输出选择 | 顶层改动 | 适用性 |
| --- | --- | --- |
| A：保持原 M31 接口 | group 输出重补 9 零，顶层主要换实例/合法模式 | 最小接入改动，S5 内部仍可缩宽 |
| B：使用 M22 接口，推荐目标 | 顶层源宽及 pad 改为参数化 | 保留紧凑 token；LZD 输入与旁带更清楚 |

常零导线或寄存器可能已被综合消除，因此 B 相对 A 的实际面积收益必须测量。推荐 B 主要为了清晰的专用合同和后续时序/功耗优化，不预填节省比例。

## 5. 全局 40 位窗口继续可配

令 W=`GLOBAL_W`，M=W−1 为全局无符号幅值窗口。E 组输入 M22；FP32 C 的现有解包幅值槽为 M32。S6 对每源先做静态低补零，保留原来的单次双向净位移：

~~~text
pad_group = M - 22             // 默认 39-22=17
pad_C = M - 32                 // 默认 39-32=7
E_max = max_active(A_raw-z)
d = E_max - (A_raw-z)
net = z-d = A_raw-E_max
aligned_mag = unsigned_shift(m << pad_source, net)
~~~

左移无损、右移 RTZ、在进入 S7 前才恢复 TC。W 必须满足 M≥max(22,32)，即 W≥33；具体 DSE 的误差目标仍需独立验收，默认保持 W=40。紧凑 E token 本身不强制把可配全局窗口减小。

S7 对 G+1 路 W-bit TC 输入求和，输出宽度 W+ceil(log2(G+1))；默认 G=4，树输出 43 位。以 `E_max` 为坐标，S6 为 S1I1F(W−2)，S7 为 S1I(1+ceil(log2(G+1)))F(W−2)。最终 RNE、渐进下溢、溢出及 C 的特殊值沿用当前 FP32 后端。

全局 anchor 不能因元素仅 4 位就改成窄指数：以 M22 为例，有限 MX scale 两侧指数和使 alpha∈[−254,254]，`A_raw`=alpha+9∈[−245,263]。NVFP4 的 `A_raw`∈[−1,27]；HiF4 连同 r∈[0,2] 后 `A_raw`∈[−87,41]。这些范围都以非零有限组 token 为前提。

考虑 z≤21，组实际指数可保守取 [−266,263]；FP32 C 的实际指数 [−149,127] 也在其中。signed 9-bit 不够表示 263，应保留至少 signed 10-bit anchor/e；d 保守上界 529，使用 unsigned 10-bit；净差运算可用 signed 11-bit 中间值。不同格式的可达组合可再收紧，但应先保留现有安全指数宽度，勿盲目截位。

## 6. 面积、功耗及验证建议

主要结构收益来自去掉 T/H/Q/INT8 路由、将 lane 乘法专用化、删除宽指数阵列及 MAX、压缩 S3/S4/S5 通路。S5 的 14×8 乘法已经在当前实现中，不应重复计作新增收益。S6 40 位对齐、FP32 C 和 S8 舍入仍有固定成本，整 DP 面积下降不会简单等于乘法器位数比例。

验证先做 E0 lane 与紧凑 group，再比较 [E1 单次 lane 移位](dp_lane_E.md)。建立从原通用 E cutpoint 到紧凑 cutpoint 的精确映射，检查 S6/S7/S8 bit-exact；独立数学 reference 的误差统计继续保留。测试覆盖三格式固定集、所有 scale 分类、HiF4 元数据、lane/组抵消、C 极端指数/特殊值和逐拍换型/复位。候选不把现有测试通过当作专用实现通过。

后续 PPA 必须分别冻结原 DP 与专用 DP、通过各自验证门禁，使用相同 E64 吞吐、L8、工具/工艺/PVT、时钟/IO/负载约束比较。时钟先用可达的 1GHz，再在同条件检查 1.41GHz；频率选择待实施时确认，不以文档推导宣称达标。面积同时报整 DP、lane/group、寄存器和后端占比；功耗在三种 E 格式的同一真实负载活动下分别测量。

待讨论的两个结构选择是：首版保留 E0 的 S3/S4 切点，还是同步尝试 E1；顶层先用 M31 兼容接口，还是直接采用推荐的 M22。建议首版采用 E0+M22，保持全局 40 位和 FP32 数值合同，先取得可验证的面积基线，再根据实际 critical path 调整流水。
