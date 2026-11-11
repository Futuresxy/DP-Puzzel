> 功能：定义 lane 规格目录与计算边界；范围：多精度 T1H2Q4E8 的 S1–S4 及 E8 优化候选；版本：v1.9；修改时间：2026-11-09 22:28:25 +0800；对应代码：[dp_lane.v](../../../verilog/lane/dp_lane.v)、[dp_mantissa_bank.v](../../../verilog/lane/dp_mantissa_bank.v)、[CModel lane.cpp](../../../cmodel/lib/lane.cpp)、[E CModel lane/lane_e.cpp](../../../cmodel/lib/lane/lane_e.cpp)、[dp_lane_e.v](../../../verilog/lane/dp_lane_e.v)；Chisel 尚未实现。

当前基础 `dp_top` 的新数值/流水边界统一见 [v1.8 合同](../dptop/dp-top-v1.8.md)；E/QE/混合顶层现有实现仍为旧版；专用文档已更新为已确认、待实现的v1.9合同，不作为新验证证据。

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

## 4. QE 专用实现

[dp_lane_qe.md](dp_lane_qe.md) 定义 Q4E8：仅保留四种 Q 与三种 E，S2 使用 8 个 4×4 乘法器（Q 激活四个），沿用多精度的 S3 局部对齐和 S4 lane 树，裁掉 T/H/INT8。v1.7.1 已实现 QE CModel/RTL并完成混合顶层验证；与 E-only 的窄树切分分别维护。

## 4. 多精度 lane 的精度寄存器门控

保持 S1–S4 算术、S/I/F、group 接口和 L8/II=1 不变。只改变寄存器保存方式，CModel 数值合同不变；不得将其视为已测功耗收益。

- S1：M32/S8 保持共用。E 指数高位不更新，最低位只在 HiF4 更新；MX/NV 消费端恢复零。分类低位保存 ZERO/FINITE；E 的分类高位和 sNaN 不更新，消费端恢复零。此开关由多精度 dp_lane 启用，QE 的解包默认行为不变。
- S2：每项乘积分为低 `2*DP_MUL_LO=8` 位与高位，按格式的有效槽捕获；E 关闭高位并在读取时补零。非 E 指数关闭于 E 请求，HiF4 仅保存一次 2 位 e2 和并广播，MX/NV 恢复零。不以乘积是否为零作为寄存器使能。
- S3：每项补码叶子分为高 `DP_E_PAIR_W+DP_E_GUARD=12` 位和低 `LEAF_W-12` 位。E 保持高位更新、关闭低位，消费端补零；默认窗口下为 12+17。原 pair/幅值 RTZ/符号恢复计算不变。依据：pair 有符号 10 位，初始低补 `LEAF_W-10` 个零，HiF4 最大右移 2 位，因此所有 E 的低 `LEAF_W-12` 位恒零，包括负数补码结果。
- 每级使能采用源级 valid/type，恢复字段采用目标级 type。valid 每拍推进，类型随有效请求更新，允许任意逐拍换型；被关闭寄存器中的旧值/初始未知值不能进入有效运算。
- 统一 DFFE 描述使能，由 DC 的标准 ICG 流程映射；禁止组合门直接切时钟。验收包括全精度/参数回归、所有格式有序切换、HiF4 metadata 和零/特殊值边界、门级一致性、时序及原生 SAIF 的实际关闭时钟统计。

补充验证入口：`python3 test/run_precision_gating.py --export-id <已验证快照>`。它不取代 `test/run_verilog.py --phase all` 的 PPA 门禁。

当前实现已通过全量/精度切换/四态验证及1GHz综合，实测结果见[精度寄存器门控功耗比较](../../../../hw/power/records/precision_register_gating_1108.md)。数值合同不变；测量结论只适用于记录的工况和负载。
