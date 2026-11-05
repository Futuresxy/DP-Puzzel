> 功能：定义 group 规格目录与计算边界；范围：两个 lane、S2 公共指数、S5 组和/scale/LZD 及 E16 优化候选；版本：v1.5.7；修改时间：2026-11-05 17:20:00 +08:00；对应代码：[dp_group.v](../../../verilog/group/dp_group.v)、[dp_scale_multiply.v](../../../verilog/arithmetic/dp_scale_multiply.v)、[CModel group.cpp](../../../cmodel/lib/group.cpp)、[E CModel group/e.cpp](../../../cmodel/lib/group/e.cpp)；E 专用 RTL 和 Chisel 尚未实现。

# group：两 lane 协作、组和与 scale

多精度基本组容量 T2H4Q8E16，含两个 [lane](../lane/README.md)。默认四组组成 T8H16Q32E64；各组不保存跨请求累加状态。C 由顶层统一处理，不复制进 group。

## 1. 多精度主实现的计算模块

| 阶段 | 计算单元 | 所有权与输出 | 详细规格 |
| --- | --- | --- | --- |
| S1 | 两侧 scale 解包 | E8 指数、I1F3 非负系数、分类 | [scale.md](scale.md) |
| S2 | 两 lane 公共指数 MAX | 同拍组合返回共同 r，不额外插拍 | [shared-align.md](shared-align.md) |
| S2 | scale 系数 4×4 及指数相加 | 8 位系数积、9 位指数和，随请求传递 | [scale.md](scale.md) |
| S5 | 两 lane TC 相加、符号/幅值分离 | 默认 32 位组 TC → 31 位幅值+符号 | [数值推导](../common/numeric-layout.md) |
| S5 | NVFP4/HiF4 共享 14×8 无符号 scale | 22 位乘积静态补零；MX 旁路 | [scale 乘法](scale.md) |
| S5 | LZD 计数、anchor 及特殊值摘要 | 原幅值/A_raw/z，同拍送到顶层 | [S5/S6 接入](../dptop/global-align.md) |

S5 幅值保持未规格化状态，LZD 只计数。输出字段、默认 M31 和参数化宽度见 [顶层模块接口](../dptop/interface.md)。小数点与指数 bias 只在规定位置融合一次；符号独立传至 S6 对齐后恢复 TC。

## 2. E16 专用优化

方案正文：[dp_group_E.md](dp_group_E.md)。对应两个 [E8 lane](../lane/dp_lane_E.md)，三格式在组规约前统一为 F4；HiF4 e2 已计入 lane coefficient，因此无跨 lane 元素指数 MAX/delta/右移。

当前 E CModel 实现的流水为 S2 乘法/pair、S3 lane 四项树、S4 两 lane TC 合并及一次组 abs、S5 scale/LZD。S4 仅需 14 位幅值+符号，S5 继续共用现有 14×8 数据乘法器；三种格式的边界、范围与 S/I/F 以专用方案为准。

用户已要求保持原 group 输出 layout 和 S5 到达拍：默认幅值 31 位、符号 1 位、anchor signed10、z 5 位、special 4 位。HiF4 融合 e2 后换用新的 coefficient/anchor/z 坐标，真实指数及 S6 对齐结果保持等价；MX/NV 的组输出坐标沿用原定义。专用 CModel 已通过数值与周期测试，专用 RTL 尚未建立。

## 3. 模块边界

lane 元素解包和乘法见 [lane](../lane/README.md)；量化块 scale 广播及组数由 [顶层输入布局](../dptop/layout-and-scales.md) 决定，不能因基本组 E16 就改变 MX 的 32 元素量化块。C 解包、G 组+C MAX、全局移位、最终树和编码由 [dptop](../dptop/README.md) 拥有。面积统计分别计数元素乘法、scale-pair 与 group-scale，避免跨流水共享资源的错误假设。
