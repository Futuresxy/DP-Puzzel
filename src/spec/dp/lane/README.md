> 功能：定义 lane 规格目录与计算边界；范围：多精度 T1H2Q4E8 的 S1–S4 及 E8 优化候选；版本：v1.6.4；修改时间：2026-11-06 15:51:16 +08:00；对应代码：[dp_lane.v](../../../verilog/lane/dp_lane.v)、[dp_mantissa_bank.v](../../../verilog/lane/dp_mantissa_bank.v)、[CModel lane.cpp](../../../cmodel/lib/lane.cpp)、[E CModel lane/lane_e.cpp](../../../cmodel/lib/lane/lane_e.cpp)、[dp_lane_e.v](../../../verilog/lane/dp_lane_e.v)；Chisel 尚未实现。

# lane：解包、元素乘法与局部规约

每条 lane 对应 32 位 A 和 32 位 B，按 datatype 解释为 T1/H2/Q4/E8，INT8 为 4 项。两个 lane 组成一个基本组；容量和位切片由 [顶层输入布局](../dptop/layout-and-scales.md) 定义。

## 1. 多精度主实现的计算模块

| 阶段 | 计算单元 | 输出与边界 | 详细规格 |
| --- | --- | --- | --- |
| S1 | dp_lane_unpack 内两侧单独解包、分类、HiF4 e1 融合 | 紧凑 M32/E20/S8 及内部分类旁带；HiF4 保留 e2 | [unpack.md](unpack.md) |
| S2 | bank 直接选紧凑字段；乘积/指数计算，unpack 内配对归约特殊值 | 无符号乘积、独立 sign、指数候选 | [multiplier-sharing.md](multiplier-sharing.md) |
| S2 侧带 | lane MAX 候选 → group MAX → 共同 r | 由 group 组合返回并在 S2 寄存，同拍无环 | [组内协作](../group/shared-align.md) |
| S3 | 幅值 RTZ、E pair/小移位、符号恢复 | 默认 29 位 TC 叶子，每 lane 四路 | [shifter-sharing.md](shifter-sharing.md) |
| S4 | 四路平衡树 | 默认 31 位 TC lane SOP，携带 r/特殊值 | [数值推导](../common/numeric-layout.md) · [逐级格式](../common/stage-formats.md) |

默认 LOCAL_W=28，叶宽=LOCAL_W+1，lane 宽=叶宽+ceil(log2(4))。T/H 的较少有效项按原格式合同补齐共享槽；各模式小数点、增长位和符号不能从总线宽度猜测。

每 lane 两套 HH/HL/LH/LL 乘法组；局部共享幅值移位器四路。scale 的两侧系数预乘和 S5 数据乘法属于 [group/scale.md](../group/scale.md)，不计入 lane 元素乘法资源。

## 2. E8 专用优化

方案正文：[dp_lane_E.md](dp_lane_E.md)。三种 E 格式保留 8 个 unsigned 4×4；删除 T/H/Q/INT8 路由及宽指数阵列。HiF4 p=e2_a+e2_b 在 lane 求和后局部左移融合，MX/NV 仅静态补零，无元素可变移位。

建议 lane 持有 S1/S2/S3 寄存器：S2 乘法后先形成四个 10 位 TC pair，S3 四项规约为 12 位 TC，S4 组合输出融合后的 14 位 TC 给 group；S4 寄存器由 group 持有。CModel 已实现这一切分，原多精度 lane 的 S4 寄存边界不因此改变。专用 RTL 已完成同源 Verilator 验证；时序由独立 DC 报告验收。

## 3. 阅读和验证边界

解包 → 乘法路由 → 局部移位/规约 → [组求和与 scale](../group/README.md)。控制/有效拍以 [顶层接口](../dptop/interface.md) 和 [流水](../dptop/pipeline.md) 为准；S/I/F、特殊值及验证规则从 [DP 总索引](../README.md) 进入。E 专用候选必须建立新的内部 cutpoint 对照，保持兼容的组输出数值语义。
