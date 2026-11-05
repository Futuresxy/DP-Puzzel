> 功能：讨论 E16 定点组规约及兼容的 group 输出；范围：HiF4 e2 内部融合、S4 组和、S5 scale/LZD、E64 八级流水与原后端复用；版本：v1.5.8；修改时间：2026-11-05 21:34:01 +08:00；对应代码：[E CModel group/e.cpp](../../../cmodel/lib/group/e.cpp)、[公共后端](../../../cmodel/lib/top/backend.cpp)、[dp_group_e.v](../../../verilog/group/dp_group_e.v)；多精度基线为 [dp_group.v](../../../verilog/group/dp_group.v)、[dp_scale_multiply.v](../../../verilog/arithmetic/dp_scale_multiply.v)、[dp_top.v](../../../verilog/top/dp_top.v)、[CModel group.cpp](../../../cmodel/lib/group.cpp)。

# E 类专用 group 设计与实现

用户已明确 group 输出 layout 与现有多精度版本对齐，group 外计算部分复用；HiF4 e2 在 lane 内融合，MX/NV 无元素指数差。CModel 已按这些边界实现 E64 的 S2 乘法+pair、S3 四项树、S4 组和/abs、S5 scale/LZD，直接复用公共后端函数。专用 RTL 已实现并通过完整 Verilator 回归；DC 采用与多精度基线相同的 N12 TT、1GHz 预算，实测结论见 [E64 综合对比](../../../../hw/dc_syn/records/e64_n12_comparison_20261105.md)。

## 1. 统一定点 E16 组

E64 = 4×E16 group，每组包含两个 E8 lane；G=1/2/4 对应 E16/E32/E64，对照原配置有 `K_E`=16G=4×`K_FP16`。默认 A/B 各 256 位。量化块 scale 与 HiF4 元数据保持 [既有广播布局](../dptop/layout-and-scales.md)，不能把 MX 的 32 元素 scale 块改为每 E16 组独立量化。

定义每 lane 原始八项有符号和为 Q，HiF4 p=e2_a+e2_b。进入组规约前统一成 F4：

~~~text
MXFP4/NVFP4: Q_lane_fixed = Q << 2    // 固定补零，无可变移位
HiF4:        Q_lane_fixed = Q << p    // p=0/1/2，lane 内一次左移
Q_group = Q_lane0_fixed + Q_lane1_fixed
value_before_scale = Q_group * 2^-4
~~~

两 lane 可直接在同一小数点下相加。HiF4 e2 的作用全部计入 coefficient，group 无须比较、回传或保存元素公共指数 r；group 的外部指数只来自块 scale。HiF4 的 e1 仍在 S1 融入元素幅值。

## 2. E64 当前 CModel / RTL 的八级流水

| 级 | 数据计算 | 寄存结果/接口 |
| --- | --- | --- |
| S1 | E/scale 解包，HiF4 e1 融合 | 4 位幅值、符号、局部 p 及 scale |
| S2 | 64 个无符号 4×4 元素乘法、32 个 signed10 pair；4 组 scale 系数预乘 | 每 lane 4×10 位 TC pair；all_negative；scale 系数 8 位 |
| S3 | 每 lane 四个 pair 的两层 TC 树 | 每 lane 12 位 TC；并行准备输出 anchor |
| S4 | HiF4 lane 内左移 p，MX/NV 静态补零；两 lane TC 相加、组 abs | 每 group 14 位幅值+符号，F4 |
| S5 | NV/HiF 14×8 无符号 scale；MX 旁路；LZD | 与原 group 完全同宽、同到达拍的 token |
| S6 | 原来的各组+C MAX、净移位与符号恢复 | 5 路默认 40 位 TC 叶子 |
| S7 | 原来的 5 项总树 | 默认 43 位 TC 总和 |
| S8 | 原来的 FP32 规格化/RNE/特殊值处理 | FP32 D、valid/last |

C 继续由顶层传递 raw32 至 S5 解包，并行于组 scale；不复制进 group。S6–S8 的 RTL 算术模块、寄存位置及 top 的补零逻辑可沿用。E-only 顶层只需接入专用 group 并限制合法请求为 E 格式/FP32 C；不要求修改后端数值算法。

S4 寄存器由 group 持有；lane 末端的左移与 group 的 TC 合并/abs 是同一 S4 组合路径。group 外部仍在 S5 到达，沿 n 接收、S1 于 n 更新、S5 于 n+4 更新、S8 于 n+7 更新，下游在 n+8 更新前观察，保持 L8/II=1。

## 3. S4/S5 的 S/I/F

S 与 I 分开计数。SM 为独立符号+无符号幅值；表中 unsigned 行另有独立符号旁带。

| 信号 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | --- | --- | --- | --- |
| S4 组和/符号幅值 | 全部 E | TC→SM | 1 | 10 | 4 | 15 |
| S5 数据乘法器幅值输入 | NVFP4/HiF4 | unsigned | 0 | 10 | 4 | 14 |
| S5 scale 系数输入 | NVFP4/HiF4 | unsigned | 0 | 2 | 6 | 8 |
| S5 scale 乘积 | NVFP4/HiF4 | unsigned | 0 | 12 | 10 | 22 |
| MX 旁路幅值 | MXFP4 | unsigned | 0 | 10 | 4 | 14 |

NV/MX 的组幅值上界 16×12²×4=9216，HiF4 上界 16×14²×4=12544，均小于 2^14。NV/HiF 共用现有 14×8 无符号 scale 乘法器；本实现进一步统一它们的输入和乘积小数点，不增大乘法器。

## 4. 与原多精度 group 对齐的输出 layout

保持现有 `dp_group` 的字段名称、位宽、时钟/复位、有效拍数、特殊值语义和“未左移幅值+原 anchor+LZD 计数”表示。输出宽度继续由原参数推导：

~~~text
M_group = LOCAL_W + 3                  // 默认 LOCAL_W=28 → M31
ANCHOR_W = 顶层按原规则提供             // 默认 10
Z_GROUP_W = ceil(log2(M_group+1))       // 默认 5
pad_MX = M_group - 14                  // 默认 17
pad_scale = M_group - 22               // 默认 9
~~~

| 输出字段 | 默认宽度 | 含义 |
| --- | --- | --- |
| `out_valid` | 1 | 与原 group 相同的 S5 有效拍 |
| `out_negative` | 1 | 独立符号，含原负零规则 |
| `out_magnitude` | 31 | MX 为 14 位幅值低补 17 零；NV/HiF 为 22 位乘积低补 9 零 |
| `out_anchor` | signed 10 | `A_raw`=`alpha_scale`−F_out+(`M_group`−1) |
| `out_z` | 5 | 对 `out_magnitude` 的 leading-zero count，零/特殊值按原规则处理 |
| `out_special` | 4 | 组级 scale 特殊值摘要；C 由顶层并行处理 |

这里 `alpha_scale`=scale_exp_a+scale_exp_b−254，不再包含 HiF4 的 r。动态 p 已消费在定点 coefficient 中。各格式的输出定点解释为：

| 输出 | 表示 | S | I | F（参数化） | 默认 F | `A_raw`（非零有限） |
| --- | --- | --- | --- | --- | --- | --- |
| MXFP4 | SM | 1 | 10 | `M_group`−10 | 21 | `alpha_scale`+9 |
| NVFP4 | SM | 1 | 12 | `M_group`−12 | 19 | `alpha_scale`+11 |
| HiF4，e2 已融合 | SM | 1 | 12 | `M_group`−12 | 19 | `alpha_scale`+11 |

HiF4 的默认 coefficient 从原 S1I10F21 换为 S1I12F19，表示同一个真实数值；对外字段 layout 和通用 token 语义保持一致。后端只需读取 magnitude/`A_raw`/z，不按 datatype 猜测固定 F，因此无需更改 S6 算术。原多精度主实现的 HiF4 格式仍按其 [逐级格式表](../common/stage-formats.md) 定义，本实现单独声明专用源的坐标。

设原通用组公共元素指数为 r∈{0,1,2}，k=2−r。对同笔非零有限 HiF4 组有：

~~~text
m_old = m_E << k
F_old = F_E + 2
alpha_old = alpha_scale + r
A_raw_E = A_raw_old + k
z_E = z_old + k
e_E = A_raw_E-z_E = e_old
~~~

因此 HiF4 的中间字段允许采用新坐标，真实指数和 S6 对齐结果保持相同。不能要求 `A_raw`/z 逐位不变后只改 coefficient。零/NaN 时仍按原条件把无效 anchor/z 设为安全值，不能用上述非零公式处理它们。

LZD 可对补零前的 14 位 MX 幅值或 22 位 scale 乘积计数：对非零 m，有 clz_M(m<<pad)=clz_W(m)，无需真的增加一个可变移位器。输出静态低零可由常量连线实现，保留宽接口不会强制内部数据通路扩回 M31。

## 5. 后端复用与指数范围

继续保留原配置合法性和外部 layout：`LOCAL_W`≥27，`GLOBAL_W`≥max(`LOCAL_W`+4,33)，默认 28/40。E 专用前端的 11/13/14 位内部幅值由格式自然范围推导，`LOCAL_W` 仅参与兼容输出容器及补零推导。

~~~text
pad_group_to_global = (GLOBAL_W-1)-M_group       // 默认 8
pad_C_to_global = (GLOBAL_W-1)-32                // 默认 7
E_max = max_active(A_raw-z)
net = A_raw-E_max
~~~

全局对齐仍为 unsigned 左移或 RTZ 右移，进入 S7 前恢复 TC。G=4 时 S7 扇入为 4 组+C=5，默认 `GLOBAL_W`=40，输出 43 位；FP32 舍入语义和特殊值不变。复用后端并不证明其 1.41GHz 时序已解决，历史 N12 结论仍只适用于原冻结输入，见 [时序记录](../../../../hw/dc_syn/records/dp_n12_timing_20261105.md)。

非零有限组的原 anchor 范围为 MX：[−245,263]；NV：[−1,27]；融合 e2 后 HiF4：[−85,41]。MX 的 263 已超过 signed 9-bit，应继续使用顶层原 `ANCHOR_W`；默认 signed 10-bit。净差保留原 signed 11-bit 中间值，不因元素仅 4 位而截窄。

## 6. 面积、功耗和验收

删除元素指数阵列、跨 lane MAX/差值/右移对齐，乘法专用化为 64 个 unsigned 4×4；S3 使用窄树，S4 以 14 位组幅值寄存，S5 直接 scale/LZD。HiF4 只在 8 个 lane 内各做一次小左移，MX/NV 完全没有元素可变移位。S6 的组+C 全局对齐仍保留。

当前实现已将第一层 pair 放在 S2，S3 只做四项规约。S2 的乘法/符号注入/pair、S4 的组加法/abs、S5 的 scale/LZD 都需要检查时序。若 S2 过紧，再讨论回退切分；保持 S4/S5 和外部 token 不动，不把功能等价推导当作频率通过证据。

无效周期用有效使能保持寄存器，MX 请求对 scale 数据乘法隔离，MX/NV 请求对 HiF4 控制路径隔离。是否采用额外 operand isolation，应比较 mux 的面积/延迟及实际活动功耗。不使用未经验证的生成时钟。

验证要求：对旧模型的 MX/NV 检查同坐标组 token；对 HiF4 检查上面的 m/A/z 转换，再检查 S6/S7/S8 bit-exact。覆盖三精度、scale 分类、HiF4 e1/e2、lane/组抵消、零符号、FP32 C、逐拍换型及复位，并按每个合法参数分别导出验证。新专用 RTL 未通过前不能用于 PPA。

PPA 对比保持相同 E64 吞吐、L8、N12 工艺/PVT、工具/约束及同一真实负载；分别报告前端与整 DP 面积/功耗。CModel 的三格式各 961 笔与原结果一致，数学 max_ulp=0；独立逐级检查和 S5 坐标/S6–S8 对照见 [E 前端测试](../../../../test/tests/test_e_frontend.py)。专用纯 Verilog 与测试已建立，综合证据见上述对比记录；真实负载功耗仍待实施。SV 历史参考不接收新 E 单元。
