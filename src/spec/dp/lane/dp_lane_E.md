> 功能：讨论 E8 专用 lane 的定点规约及 HiF4 e2 融合；范围：S1–S3 寄存、S4 lane 内组合左移、E64 前端流水；版本：v1.7.2；修改时间：2026-11-08 02:24:09 +0800；对应代码：[E CModel lane/lane_e.cpp](../../../cmodel/lib/lane/lane_e.cpp)、[dp_lane_e.v](../../../verilog/lane/dp_lane_e.v)、[dp_lane_unpack_e.v](../../../verilog/unpack/dp_lane_unpack_e.v)；多精度基线为 [dp_lane.v](../../../verilog/lane/dp_lane.v)、[dp_mantissa_bank.v](../../../verilog/lane/dp_mantissa_bank.v)、[CModel lane.cpp](../../../cmodel/lib/lane.cpp)。

# E 类专用 lane 设计与实现

用户已确认采用 HiF4 先求和再移位，并使 group 输出兼容现有多精度版本；进一步明确可将 HiF4 e2 融入定点 coefficient，删除两 lane 间的指数 MAX/差值/右移对齐。按用户授权，CModel 已实现所选 S2 乘法+第一层 pair、S3 四项规约切分，S4/S5 接口拍数保持不变。专用 RTL 已实现并通过 Verilator 回归；时序和面积按对应 DC 结果解释；现有设计族为 v1.7，原多精度前端的数值与流水合同保持。

## 1. E64 组织与 e2 融合

E64 = 4 个 E16 group = 8 个 E8 lane，每拍完成 64 对元素乘积和，再与一份 FP32 C 相加。保留 MXFP4、NVFP4 和项目当前定义的 HiF4，三类可逐拍切换；每笔 A/B 同格式。输入布局和 scale 共享关系遵循 [原合同](../dptop/layout-and-scales.md)。

MXFP4/NVFP4 元素幅值 coefficient 为 {0,1,2,3,4,6,8,12}，定点格式 I3F1；HiF4 幅值为 (raw&7)×2^e1，格式 I2F2。HiF4 每侧 e2 共享 8 个元素，令 p=e2_a+e2_b，p∈{0,1,2}。原始带符号乘积为 q_i：

~~~text
MXFP4/NVFP4: element_product = q_i * 2^-2
HiF4:        element_product = (q_i << p) * 2^-4

HiF4 lane:   sum_i(q_i << p) = sum_i(q_i) << p
~~~

因此 group 可以在固定二进制小数点下直接累加，无需共同元素 anchor、lane candidate active 或两 lane 间 MAX/delta。HiF4 p 是 lane 内部的局部控制，在 coefficient 中消耗，不传给 group 作为指数。

代数上等价于将 e2 融入每个 product。当前物理实现为 lane 求和后一次左移：S2 乘法后两两形成 10 位 TC pair 并寄存，S3 采用四项窄树，S4 在 lane 末端组合左移 0/1/2 位。MX/NV 仅静态补两个低零，以便统一成相同的 F4；静态补零是连线，无可变移位器。

## 2. 当前 CModel / RTL 的 S1–S5 划分

| 级 | lane 数据路径 | group/旁带 | 主要寄存数据 |
| --- | --- | --- | --- |
| S1 | E 解包，HiF4 e1 融入 4 位幅值 | scale 解包、采样控制 | A/B 幅值与符号、局部 p 信息 |
| S2 | 每 lane 8 个无符号 4×4，注入乘积符号，第一层 pair | scale 4×4 系数积及指数和 | 每 lane 4×10 位 TC pair，及 `all_negative` |
| S3 | 四个 pair 的两层平衡规约，保留 TC | 提前计算 scale 修正后的输出 anchor | 每 lane 12 位 TC，及 p/零符号旁带 |
| S4 | lane 内 HiF4 TC 左移 p；MX/NV 静态补 2 零 | 两 lane TC 相加，组和后分离符号/幅值 | 每 group 14 位幅值+独立符号 |
| S5 | lane 不再计算 | NV/HiF 14×8 scale 或 MX 旁路；LZD；兼容输出 | 与原多精度 group 相同的 S5 token |

S2 pair 与 S3 四项树共同完成 E8 lane 规约；S4 完成 E16 group 规约及一次组 abs。S4 的组幅值已经准备好，S5 不再串联组加法及 abs。S6–S8 与 C 路径继续使用原后端，见 [group 接入合同](../group/dp_group_E.md)。

模块边界也随之调整：lane 持有 S1/S2/S3 寄存器，其末端左移为 S4 组合逻辑；组模块在同一个 S4 边沿寄存两 lane 合并结果。不能先在 lane 内增加 S4 输出寄存器，再指望 group 合并仍属于 S4。对外 group 仍在 S5 输出，不改变原后端的到达拍数。

### 独立 E 解包模块

`dp_lane_e` 内分别实例化 `dp_lane_unpack_e operand_unpack_a/operand_unpack_b`；每份处理一个32位操作数（8个FP4元素）。组合输入为 `in_data[31:0]`、datatype和两个HiF4 e1位，输出为8×4位 unsigned magnitude及8位独立符号，保留负零符号。MX/NV 输出 S0I3F1，HiF4 e1 融合后输出 S0I2F2，数值合同不变。

`dp_lane_unpack_e` 不持有时钟、复位、valid或寄存器，延迟为组合逻辑；调用者在原 S1 边界按有效使能采样。lane 继续持有 `a/b_mantissa_s1_q`、`a/b_sign_s1_q`，同步复位屏蔽采样，无效周期保持数据。HiF4 e2 的 p 生成/传递仍属于 lane，scale 解包仍属于 group。单独 module 不等于额外流水级，整个 DP 保持 L8/II1。

多精度版原有 `dp_lane_unpack` 保持原实现（含其 S1 寄存器），不为结构对称而移动寄存器或混入多精度解码路径。新层级只改变 E 代码组织；已有 DC 面积/时序仅属于其原快照，不自动继承到新源文件指纹。

## 3. S/I/F 与自然增长

S 不计入 I。TC 为二补码，SM 为独立符号加幅值；乘法器的符号单独携带。以下仅计数值位，不含控制和指数旁带。

| 阶段/信号 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 乘法器幅值输入 | MXFP4/NVFP4 | unsigned | 0 | 3 | 1 | 4 |
| S1 乘法器幅值输入 | HiF4，e1 已融合 | unsigned | 0 | 2 | 2 | 4 |
| S2 乘法组合输出 | MXFP4/NVFP4 | unsigned | 0 | 6 | 2 | 8 |
| S2 乘法组合输出 | HiF4 | unsigned | 0 | 4 | 4 | 8 |
| S2 pair 寄存输出 | MXFP4/NVFP4 | TC | 1 | 7 | 2 | 10 |
| S2 pair 寄存输出 | HiF4 | TC | 1 | 5 | 4 | 10 |
| S3 lane 原始和 | MXFP4/NVFP4 | TC | 1 | 9 | 2 | 12 |
| S3 lane 原始和 | HiF4 | TC | 1 | 7 | 4 | 12 |
| S4 lane 融合 p 或静态补零后 | 全部 E | TC | 1 | 9 | 4 | 14 |
| S4 group 合并/符号分离后 | 全部 E | TC→SM | 1 | 10 | 4 | 15 |

~~~text
W_mant = 4; W_product = 8
N_pair = 8/2 = 4
W_pair_tc = W_product + 1 + ceil(log2(2)) = 10
W_lane_raw_tc = W_pair_tc + ceil(log2(N_pair)) = 12
W_lane_raw_mag = W_lane_raw_tc - 1 = 11
W_lane_fused_mag = W_lane_raw_mag + max(p) = 13
W_group_mag = W_lane_fused_mag + ceil(log2(2)) = 14
~~~

HiF4 原始 lane 和幅值上界 8×14²=1568，左移 p 后不超过 6272；group 不超过 12544。MX/NV 原始 lane 幅值不超过 8×12²=1152，静态补两零后不超过 4608，group 不超过 9216。均满足上述位宽。HiF4 左移增加整数范围，F 保持 4；MX/NV 静态低补零将 F2 变为 F4，两条路径精确统一到 I9F4。

若在 S2 对每个 HiF4 product 左移，乘积槽需要 10 位、后续 lane 树需要 14 位；共有 64 个小移位。求和后再左移只需 8 个 12→14 位 TC 小移位，S2 pair 寄存与 S3 树的数据通路保持较窄。这是结构推导，实际面积与时序仍需同约束综合确认。

## 4. 算术和控制要求

每个无符号 8 位乘积先按独立 XOR 符号解释为 9 位 TC，再以足够位宽扩展，两个乘积相加得到 10 位 TC pair。HiF4 pair 的幅值上界为 2×14²=392，MX/NV 为 2×12²=288，均在 signed10 范围内。S2 注册四个 pair，S3 采用 10→11→12 位的两层平衡树；不能写成串行相加链。也可比较 CSA 压缩后一次最终 CPA，但是否更优由映射证据判断。保持 TC 直到组和后再做一次 abs，省去重复的 lane abs 和符号恢复。

S4 对 HiF4 先将 12 位 TC 符号扩展到 14 位，再左移 p；MX/NV 直接将 12 位 TC 低拼两个零。这里左移为已证明范围内的精确整数乘 2^p，没有截断。两个 14 位 TC 相加得到 15 位组和，随后安全求绝对值并寄存 14 位幅值与独立符号。其结果与无符号幅值左移、带符号合并相等；需要在 RTL 中显式定义扩展和结果宽度。

`all_negative` 按所有原始乘积符号归约，包括零元素；group 的精确零符号继续使用原合同。不得用 lane 和的 sign bit 替代全部元素的零符号旁带。scale 乘零也保留原组和符号规则。

p、datatype、scale、valid、特殊值和零符号信息必须跟随本笔数据。同步低有效 `rst_n` 清除有效控制并取消在途，无效周期数据保持。删去指数 MAX 后不需要 lane 之间的独立握手；顶层仍只有一次 A/B/C 原子接收。

## 5. 寄存成本与时序待验收项

当前采用的切分为：S2 元素乘法+第一层 pair，S3 四项 TC 树，S4 小左移+两 lane TC 合并+组 abs，S5 scale+LZD。S3 由完整八项树缩为四项树；S2 增加符号注入与 pair 加法，必须检查乘法后串联算术的组合预算。

| S2 数值寄存候选 | 每 lane 数据位 | E64 八个 lane 数据位 |
| --- | --- | --- |
| 原始 8 个幅值乘积+8 个独立符号 | 8×8+8=72 | 576 |
| 当前候选：四个 signed10 pair | 4×10=40 | 320 |

差额为 256 个逻辑数据寄存位。valid、模式、p、`all_negative` 及 scale 等旁带另计；这不是实际触发器数量或面积/功耗测量。pair 求和丢弃了单项符号表达，因此必须在合并前按原始八个乘积符号生成 `all_negative`，不能从四个 pair 的 sign bit 还原零符号语义。

若 S2 经综合后过紧，可回退为乘法独立、S3 八项树的切分，S4/S5 及 group 对外布局保持不变；当前不同时实现两套前端，不预先宣称某个切分达到 1GHz 或 1.41GHz。

若后续静态配置仅包含 MX/NV，e1/e2 解包与 8 个小左移器可以整体裁掉，group 就是统一定点规约加 scale。运行时选择 MX/NV 只使 HiF4 路径旁路或隔离，不等于物理逻辑被删除；是否新增该能力配置另行定义。

## 6. 验证边界

后续专用实现先验证 product 级融合与 lane 和后融合的等价，再验证 group token 的数值坐标及 S6/S7/S8 结果。S3/S4 内部切点改变后，应建立新的 trace 对照，不能继续要求旧切点原始比特相同。group 的字段宽度和语义保持原接口，HiF4 的数值坐标换算见配套文档。

覆盖所有元素编码乘积、HiF4 e1/e2 组合、严重抵消、正负零、scale 分类、C 特殊值、逐拍换型、气泡和复位；G=1/2/4 及原合法窗口分别验证。当前 CModel 已通过三格式各 961 笔及 6 项 E 前端测试：独立 Fraction 检查 pair/lane/group 数值、同多精度模型比较兼容 S5 坐标和 S6–S8；覆盖 K4/8/16、27/40、28/48、32/64 及 L8/L9。测试入口为 [test_e_frontend.py](../../../../test/tests/test_e_frontend.py)。专用 RTL 已通过同源 Verilator 检查；完整覆盖、断点及结果见 [E64 报告](../../../../test/results/e64-v1.5.8.md)。

专用 CModel 与纯 Verilog 已实现；冻结的 SystemVerilog 历史目录不添加 E-only 模块，详见 [维护边界](../../../verilog/systemverilog/README.md)。

## 7. E 扩展的进一步面积优化

当前窄 pair/树和 lane 求和后融合 e2 已实现；不能重复列为新收益。新增优化继续支持 MXFP4、NVFP4、HiF4，不增加 T/H/Q/INT8，保持本页 S2/S3/S4 所有权和组 S5 接口。

优先候选为在 S1 前对 A/B 符号做 XOR，只寄存八个乘积符号，替代两组各八个操作数符号。若无其他消费者，逻辑上每 lane 减少八个符号寄存位，四个扩展 E group 的八条 lane 共减少 64 位；原始零项符号和 all_negative 必须仍然正确。XOR 前移需检查 S1 时序，面积收益待综合网表确认。

当前范围决定的必要宽度如下；不能为压面积直接少留一位：

| 数值节点 | HiF4 最大幅值 coefficient | 当前必要表示 |
| --- | ---: | --- |
| 单乘积 | 14×14=196 | unsigned8；注入符号为 signed9 |
| pair | 2×196=392 | signed10 |
| lane 八项和 | 8×196=1568 | signed12 |
| lane 融合 e2 后 | 1568×4=6272 | signed14 |
| 两 lane 组和 | 2×6272=12544 | signed15；abs 后 unsigned14 |

后续可独立评估小系数乘法实现：E2M1 使用小尾数与指数重构，或 HiF4 同一 e1 粒度内先做未移位乘积的 pair，再施加共同 e1 和。后者仅在两项共享同一个 e1_a/e1_b、无中间截断、输出宽度足够时成立；跨粒度不能合并。这些是未测候选，额外移位/MUX 可能抵消乘法节省，不替换当前已验证实现。需穷举元素编码和 e1/e2、核对 S2/S3 精确值，并在同工况 DC 下比较。

S1 符号压缩与乘法候选分开提交/验证，不能将逻辑寄存位下降直接换算成实际面积或功耗。整机目标和测量约束见 [混合顶层优化](../dptop/mixed-precision-expansion.md#10-独立面积优化版本与验收)。
