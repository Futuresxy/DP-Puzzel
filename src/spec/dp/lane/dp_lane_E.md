> 功能：讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合；范围：S1–S3 寄存、S4 lane 内组合左移、E64 前端流水；版本：v1.5.4；修改时间：2026-11-05 14:16:26 +08:00；对应代码：专用实现尚未建立；推导基线为 [dp_lane.v](../../../verilog/lane/dp_lane.v)、[dp_mantissa_bank.v](../../../verilog/lane/dp_mantissa_bank.v)、[CModel lane.cpp](../../../cmodel/lib/lane.cpp)。

# E 类专用 lane 讨论稿

用户已确认采用 HiF4 先求和再移位，并使 group 输出兼容现有多精度版本；进一步明确可将 HiF4 e2 融入定点 coefficient，删除两 lane 间的指数 MAX/差值/右移对齐。本文给出对应的八级流水建议，具体 S2–S4 切点仍待讨论。专用 RTL/CModel 尚未实现，时序和 PPA 尚未测量；现有多精度主实现保持 v1.5 架构及 v1.5.1 实现映射。

## 1. E64 组织与 e2 融合

E64 = 4 个 E16 group = 8 个 E8 lane，每拍完成 64 对元素乘积和，再与一份 FP32 C 相加。保留 MXFP4、NVFP4 和项目当前定义的 HiF4，三类可逐拍切换；每笔 A/B 同格式。输入布局和 scale 共享关系遵循 [原合同](../dptop/layout-and-scales.md)。

MXFP4/NVFP4 元素幅值 coefficient 为 {0,1,2,3,4,6,8,12}，定点格式 I3F1；HiF4 幅值为 (raw&7)×2^e1，格式 I2F2。HiF4 每侧 e2 共享 8 个元素，令 p=e2_a+e2_b，p∈{0,1,2}。原始带符号乘积为 q_i：

~~~text
MXFP4/NVFP4: element_product = q_i * 2^-2
HiF4:        element_product = (q_i << p) * 2^-4

HiF4 lane:   sum_i(q_i << p) = sum_i(q_i) << p
~~~

因此 group 可以在固定二进制小数点下直接累加，无需共同元素 anchor、lane candidate active 或两 lane 间 MAX/delta。HiF4 p 是 lane 内部的局部控制，在 coefficient 中消耗，不传给 group 作为指数。

代数上等价于将 e2 融入每个 product。建议物理实现为 lane 求和后一次左移：S2 仍寄存 8 位原始乘积，S3 采用窄树，S4 在 lane 末端组合左移 0/1/2 位。MX/NV 仅静态补两个低零，以便统一成相同的 F4；静态补零是连线，无可变移位器。

## 2. 建议的 S1–S5 划分

| 级 | lane 数据路径 | group/旁带 | 主要寄存数据 |
| --- | --- | --- | --- |
| S1 | E 解包，HiF4 e1 融入 4 位幅值 | scale 解包、采样控制 | A/B 幅值与符号、局部 p 信息 |
| S2 | 每 lane 8 个无符号 4×4，符号 XOR | scale 4×4 系数积及指数和 | 8×8 位乘积、8 位符号 |
| S3 | 8 项带符号规约，保留 TC | 提前计算 scale 修正后的输出 anchor | 每 lane 12 位 TC，及 p/零符号旁带 |
| S4 | lane 内 HiF4 TC 左移 p；MX/NV 静态补 2 零 | 两 lane TC 相加，组和后分离符号/幅值 | 每 group 14 位幅值+独立符号 |
| S5 | lane 不再计算 | NV/HiF 14×8 scale 或 MX 旁路；LZD；兼容输出 | 与原多精度 group 相同的 S5 token |

S3 是完整 E8 lane 规约；S4 完成 E16 group 规约及一次组 abs。S4 的组幅值已经准备好，S5 不再串联组加法及 abs。S6–S8 与 C 路径继续使用原后端，见 [group 接入合同](../group/dp_group_E.md)。

模块边界也随之调整：lane 持有 S1/S2/S3 寄存器，其末端左移为 S4 组合逻辑；组模块在同一个 S4 边沿寄存两 lane 合并结果。不能先在 lane 内增加 S4 输出寄存器，再指望 group 合并仍属于 S4。对外 group 仍在 S5 输出，不改变原后端的到达拍数。

## 3. S/I/F 与自然增长

S 不计入 I。TC 为二补码，SM 为独立符号加幅值；乘法器的符号单独携带。以下仅计数值位，不含控制和指数旁带。

| 阶段/信号 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 乘法器幅值输入 | MXFP4/NVFP4 | unsigned | 0 | 3 | 1 | 4 |
| S1 乘法器幅值输入 | HiF4，e1 已融合 | unsigned | 0 | 2 | 2 | 4 |
| S2 原始乘积 | MXFP4/NVFP4 | unsigned | 0 | 6 | 2 | 8 |
| S2 原始乘积 | HiF4 | unsigned | 0 | 4 | 4 | 8 |
| S3 lane 原始和 | MXFP4/NVFP4 | TC | 1 | 9 | 2 | 12 |
| S3 lane 原始和 | HiF4 | TC | 1 | 7 | 4 | 12 |
| S4 lane 融合 p 或静态补零后 | 全部 E | TC | 1 | 9 | 4 | 14 |
| S4 group 合并/符号分离后 | 全部 E | TC→SM | 1 | 10 | 4 | 15 |

~~~text
W_mant = 4; W_product = 8
W_lane_raw_tc = W_product + 1 + ceil(log2(8)) = 12
W_lane_raw_mag = W_lane_raw_tc - 1 = 11
W_lane_fused_mag = W_lane_raw_mag + max(p) = 13
W_group_mag = W_lane_fused_mag + ceil(log2(2)) = 14
~~~

HiF4 原始 lane 和幅值上界 8×14²=1568，左移 p 后不超过 6272；group 不超过 12544。MX/NV 原始 lane 幅值不超过 8×12²=1152，静态补两零后不超过 4608，group 不超过 9216。均满足上述位宽。HiF4 左移增加整数范围，F 保持 4；MX/NV 静态低补零将 F2 变为 F4，两条路径精确统一到 I9F4。

若在 S2 对每个 HiF4 product 左移，乘积槽需要 10 位、后续 lane 树需要 14 位；共有 64 个小移位。求和后再左移只需 8 个 12→14 位 TC 小移位，S2/S3 的数据通路保持较窄。这是结构推导，实际面积与时序仍需同约束综合确认。

## 4. 算术和控制要求

S3 的八项带符号树不能写成七次串行加法。平衡树的 TC 自然增长为 9→10→11→12 位；也可比较 CSA 压缩后一次最终 CPA。保持 TC 直到组和后再做一次 abs，省去重复的 lane abs 和符号恢复。

S4 对 HiF4 先将 12 位 TC 符号扩展到 14 位，再左移 p；MX/NV 直接将 12 位 TC 低拼两个零。这里左移为已证明范围内的精确整数乘 2^p，没有截断。两个 14 位 TC 相加得到 15 位组和，随后安全求绝对值并寄存 14 位幅值与独立符号。其结果与无符号幅值左移、带符号合并相等；需要在 RTL 中显式定义扩展和结果宽度。

`all_negative` 按所有原始乘积符号归约，包括零元素；group 的精确零符号继续使用原合同。不得用 lane 和的 sign bit 替代全部元素的零符号旁带。scale 乘零也保留原组和符号规则。

p、datatype、scale、valid、特殊值和零符号信息必须跟随本笔数据。同步高有效复位清除有效控制并取消在途，无效周期数据保持。删去指数 MAX 后不需要 lane 之间的独立握手；顶层仍只有一次 A/B/C 原子接收。

## 5. 时序待讨论项

当前建议将 S3 定为八项 TC 树，S4 定为小左移+两 lane TC 合并+组 abs，S5 定为 scale+LZD。这样缩短原 S5 串行链，但 S3 增加了规约深度，应作为前端首要检查点。

若 S3 时序紧，可将第一层 pair 加法前移至 S2，S3 只处理四项 TC 规约，后端 S4/S5 不动。这会在 4×4 乘法之后增加 pair 算术，是否有预算须实测。具体切点尚未批准，不提前承诺 1GHz 或 1.41GHz。

若后续静态配置仅包含 MX/NV，e1/e2 解包与这 8 个小左移器可以整体裁掉，group 就是统一定点规约加 scale。运行时选择 MX/NV 只使 HiF4 路径旁路或隔离，不等于物理逻辑被删除；是否新增该能力配置另行定义。

## 6. 验证边界

后续专用实现先验证 product 级融合与 lane 和后融合的等价，再验证 group token 的数值坐标及 S6/S7/S8 结果。S3/S4 内部切点改变后，应建立新的 trace 对照，不能继续要求旧切点原始比特相同。group 的字段宽度和语义保持原接口，HiF4 的数值坐标换算见配套文档。

覆盖所有元素编码乘积、HiF4 e1/e2 组合、严重抵消、正负零、scale 分类、C 特殊值、逐拍换型、气泡和复位；G=1/2/4 及原合法窗口分别验证。当前仅有数值推导和现有模型 trace 对照，专用 RTL 验收尚未发生。
