> 功能：定义 scale 后实际指数检测与合并对齐；范围：S5/S6 主方案及对照、LZD、合并移位、粗粒度检测、指数范围和特殊值；版本：v1.5.4；修改时间：2026-11-05 14:16:26 +08:00；对应代码：[CModel lib/group.cpp](../../../cmodel/lib/group.cpp)；分组主方案手写 RTL：[dp_top.v](../../../verilog/top/dp_top.v)；Chisel 尚未实现。

# dptop：组结果与 C 的全局对齐

当前方案在 scale 乘法后检测最高有效位，S5 仅保存 LZD 计数，S6 把左规格化与右对齐合成一次双向移位。该处理改善全局窗口利用率，不恢复 S3 已经截去的位。

## 1. 数值坐标

令有限非零组的原幅值为 m，宽度 M，小数位 F，无偏参考指数α。其数值与容器 anchor 为：

```text
value = (-1)^sign * m * 2^(α-F)
A_raw = α-F+(M-1)
z = clz_M(m)
e = A_raw-z
```

A_raw 是原容器最高物理位的权重，e 才是实际最高非零位的指数。只比较 A_raw 会在强抵消后浪费窗口；所有有限非零源均须独立检测，不能只检测原 anchor 最大的源。

## 2. S5/S6 合同

S5 顺序为两 lane 合并→分离符号和幅值→无符号 scale 乘法或旁路→LZD 计数。符号旁带在 S6 对齐后用于恢复补码。出口保留`sign,m_raw,A_raw,z,zero/special,ctrl,valid/last`，幅值不动态左移。默认组 M31、A_raw signed10、z unsigned5。

C 在 S5 独立解包。FP32 自然 M24 低补 8 个结构零进入 M32/F31，正规 z=0，非正规非零 z=1..23；A_raw 为有效无偏指数。INT32 C 为 M32/F0，旁路浮点检测。

对 G 个组和 C，先排除零/特殊源，再计算：

```text
E_max = max(e_i)
d_i = E_max-e_i >= 0
net_i = z_i-d_i = A_raw_i-E_max
x_i = m_raw_i << (W-M_i)       // 静态补零；W默认39
if net_i >= 0: y_i = x_i << net_i
else:          y_i = x_i >> (-net_i)
value_aligned_i = (-1)^sign_i * y_i * 2^(E_max-(W-1))
```

正 net 不超过 z，因此只移出前导零；负 net 执行无符号幅值 RTZ，随后恢复补码。右移量达到 W 时结果为零，不能把完整 d 或 net 截短后参与运算。S6 可直接算 A_raw−E_max，trace 仍保留 z/e/d/net。

## 3. 等价关系与边界

精确先左后右的结果为`((m<<z)<<(W-M))>>d`。将方向相反的位移合并得到上式，前提是中间不截窄有效位、不增加舍入。CModel 用独立公式检查两者一致。

零组、抵消组及特殊源使用安全占位 A_raw=0、z=0，由独立 active 屏蔽 MAX；不使用 clz(0)产生普通指数。S8 仍对最终总和执行 LZD/norm/RNE 和特殊结果 mux。

默认保守范围为 A_raw∈[−278,288]、e∈[−308,288]、d∈[0,596]；减法及净位移临时量须加宽，详见[逐级格式](../common/stage-formats.md)。S8 加输出 bias 之前也要检查正常、非正规及溢出边界。

## 4. 保留的探索方案

| 方案 | 数值关系 | 后续评估 |
| --- | --- | --- |
| 精确计数＋一次双向移位 | 当前主方案 | LZD、方向路由、MAX 路径及功耗 |
| 完整左规格化后再右移 | 同宽度下与主方案等价 | 两段移位器、寄存与时钟成本 |
| 粗粒度最高非零块检测 | 公共指数可高估至多块宽−1 位 | 需新的精度合同，当前未采用 |
| 不检测、扩大窗口 | 坐标可正确，但可能浪费前导零空间 | 全局移位、树和寄存均变宽 |

没有门级证据前不预设面积或功耗排名。比较必须保持数值窗口、K、工艺/PVT、II 与负载一致，并明确 L8/L9 的延迟差异。

## 5. S6 的共享资源与窗口

S5 组输出 sign/原幅值/A_raw/z，S6 以 e=A_raw-z 比较 MAX，再用 net=z-d 一次双向移位；默认全局幅值 39 位，G+1 份物理单元按格式经输入 mux 共享。S5 无动态左移。

当前结构按 N=G+1 个并行对齐源预算，主配置五路；MAX、delta 与移位在 S6 内。INT8/INT32 走可逆结构落位旁路，宽移位器隔离。S3 和 S6 同拍处理不同请求，不能在 II=1 下把两级物理移位器时分复用为同一套。

全局窗口与局部窗口是两个明确参数，分别影响不同截断点；不得隐含绑定为同一宽度。每个源必须满足 pad≥0，精度目标及合法参数检查见 [逐级数值](../common/numeric-layout.md) 和 [出口表](../common/stage-formats.md)。

## 6. 双向移位网络与对照

S5 只对 scale 后幅值检测 z 并保留原始幅值，S6 用 net=z-d=A_raw-E_max 一次双向移动，取消 S5 动态左移器。不是将两个并发流水阶段的现有单元时分复用，而是把同一请求的两次位移代数合并。局部 S3 的独立资源见 [lane/shifter-sharing.md](../lane/shifter-sharing.md)。

S6 每个源（G 组+C）有一套 W 位双向幅值移位器，默认 W=39。当前 RTL 的 dp_bidir_shift 接收 in_magnitude[W] 和 signed in_net[NET_W]，输出 out_magnitude[W]；默认 NET_W=11。方向与移位量从完整 net 派生，输入隔离由上层 dp_global_align 承担。上层按完整 signed net 判方向，右移量≥W 输出 0；左移量≤源 z，必须检查不移出有效位。z/d/net 与方向必须来自同一请求。INT 旁路，未使用单元输入隔离。

可用固定 bit-reverse 接线、输入/输出方向 mux 和一套逻辑右移网络实现双向移动；右移 RTZ，左移精确。后续需检查综合结构确实共享，而非两套完整 barrel 后 mux 输出。理想 W 位、k=ceil(log2(W))简单网络：单向约 Wk 个 2:1mux、两套方向约 2Wk、反序共享约 Wk+2W。该结构估算不包含边缘恒零优化、控制和物理布线，不是面积/功耗结果；不同位宽的 S5 左移和 S6 右移需分别计数。

[Pillmeier/Schulte/Walters 的原始论文](https://www.princeton.edu/~rblee/ELE572Papers/Fall04Readings/Shifter_Schulte.pdf) 给出 data-reversal 等结构比较，说明双向操作可共享网络；不能移植其工艺测量到本 DP。相比双单向方案，本方案省去独立 S5 左移及相关路由，但 S6 增加方向选择、e 生成和控制路径；在 1.41 GHz 下可能产生不同关键路径，功耗需负载活动证据。

当前首选为精确计数+一次双向；完整左移再右移保留为等价 PPA/时序对照，粗粒度版仅候选。比较时保持窗口、数值、K、工艺/PVT 和 II 一致，若延迟不同必须显式报告，禁止把不同 pipeline 的寄存/时钟成本遗漏。
