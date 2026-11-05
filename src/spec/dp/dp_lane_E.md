> 功能：讨论 E8 专用 lane 的精简数据通路；范围：MXFP4/NVFP4/HiF4、S1–S4、精确局部对齐；版本：v1.5.2；修改时间：2026-11-05 13:33:21 +08:00；对应代码：专用实现尚未建立；推导基线为 [dp_lane.v](../../verilog/lane/dp_lane.v)、[dp_mantissa_bank.v](../../verilog/lane/dp_mantissa_bank.v)、[CModel lane.cpp](../../cmodel/lib/lane.cpp)。

# E 类专用 lane 讨论稿

状态：候选方案，待用户讨论确认；没有新增 RTL/CModel，也没有专用设计的 PPA 测量。现有多精度 DP 继续遵循 v1.5 架构及 v1.5.1 实现映射。目标是保持当前 E 类数值语义、每 lane 每拍 8 对元素和 L8/II=1，通过专用乘法器、窄寄存器及小范围移位减少面积与活动。

## 1. 范围与结构

E 包括 MXFP4 E2M1、NVFP4 E2M1 和项目当前定义的 HiF4。A/B 每笔同格式，三类可逐拍切换。HiF4 沿用现有 e1/e2 和 E6M2 定义，不另造编码。C/D 为 FP32，专用 DP 不支持 INT8/INT32。输入布局和量化块 scale 共享关系保持 [原合同](layout-and-scales.md)。

~~~text
S1 E 解包：8×(4-bit 幅值 + 符号)，HiF4 e1 融入幅值
         ↓
S2 8× unsigned 4×4 → 8×8-bit 乘积，符号 XOR
   同时形成 lane e2 指数和及 active → group 两路 MAX
         ↓
S3 4×有符号 pair → abs → 补 2 个保护零 → HiF4 0/1/2 右移 → 恢复符号
         ↓
S4 四路平衡加法树 → 14-bit 有符号 lane SOP
~~~

lane 仍占 S1–S4。两个 lane 组成 E16 基本组，见 [dp_group_E](dp_group_E.md)。G 个组组成 E(16G) DP；默认 G=4，即 E64，对应现有 `K_FP16`=16 的 E 吞吐。

## 2. 可删除与保留的逻辑

| 当前通用 lane | E 专用建议 | 原因 |
| --- | --- | --- |
| T/H/Q/INT8 解包、分类及选择 | 只保留 E2M1 与 HiF4 解包 | E 元素没有独立 NaN/Inf 编码 |
| 每 lane 两组 HH/HL/LH/LL 混合宽度乘法及重组 | 8 个无符号 4×4 乘法器 | 三种 E 格式的解包幅值都能装入 4 位 |
| 8 个通用元素指数和及 lane MAX | 一个 2-bit lane 指数和 | MX/NV 恒为 0；HiF4 同 lane 的 e2 相同 |
| 4 个通用 `LOCAL_W` 幅值移位器 | 4 个 11-bit 幅值、仅选 0/1/2 的右移器 | HiF4 两侧 e2 各 1 位；MX/NV 旁路 |
| 多精度树宽及格式 mux | 专用 12→14-bit 树 | E 的结构低零可以省去 |
| 请求/符号/零语义及有效位 | 保留并缩短控制表示 | 逐拍换型、取消在途和负零仍要正确 |

上述宽度是 RTL 的逻辑容器对照；DC 可能已消除部分常零位，不能据此直接换算实际触发器或面积节省。元素分类逻辑可删，scale/C 的 NaN/Inf、payload 合法性检查仍由组和顶层承担。

## 3. S/I/F 与位宽推导

S 不包含在 I 内。TC 为二补码；SM 为独立符号加无符号幅值。S0 行的符号在旁带中传递。表中为本候选的物理数值宽度，不含 valid、指数等控制。

| 阶段/信号 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 乘法幅值输入 | MXFP4/NVFP4 | unsigned | 0 | 3 | 1 | 4 |
| S1 乘法幅值输入 | HiF4（融合 e1） | unsigned | 0 | 2 | 2 | 4 |
| S2 乘法幅值输出 | MXFP4/NVFP4 | unsigned | 0 | 6 | 2 | 8 |
| S2 乘法幅值输出 | HiF4 | unsigned | 0 | 4 | 4 | 8 |
| S3 pair 原始和 | MXFP4/NVFP4 | TC | 1 | 7 | 2 | 10 |
| S3 pair 原始和 | HiF4 | TC | 1 | 5 | 4 | 10 |
| S3 补零/精确对齐后叶子 | MXFP4/NVFP4 | TC | 1 | 7 | 4 | 12 |
| S3 补零/精确对齐后叶子 | HiF4 | TC | 1 | 5 | 6 | 12 |
| S4 lane SOP | MXFP4/NVFP4 | TC | 1 | 9 | 4 | 14 |
| S4 lane SOP | HiF4 | TC | 1 | 7 | 6 | 14 |

MX/NV 元素幅值 coefficient 为 {0,1,2,3,4,6,8,12}，HiF4 融合 e1 后为 (raw&7)×2^e1，最大 14。每个 pair 求两个带符号乘积和：10 位 TC 足够。取幅值时用安全扩展中间值，随后补两个低零：幅值装入 11 位，另有一个符号位，组成 12 位叶子。四叶子树增长两位得到 14 位。

参数从结构派生，不延用为了 T/H/Q 配置的 `LOCAL_W`=28：

~~~text
N_E = 8                     // 每 lane 元素数，保持现有 E8
N_pair = N_E / 2 = 4
W_mant = 4; W_product = 2*W_mant = 8
W_pair_tc = W_product + 2 = 10
GUARD = max(e2A+e2B) - min(e2A+e2B) = 2
W_leaf_tc = W_pair_tc + GUARD = 12
W_lane_tc = W_leaf_tc + ceil(log2(N_pair)) = 14
~~~

HiF4 的 F=6 是以公共 e2 anchor 为坐标的固定小数点；右移不会丢位，因为预留 2 个保护低零，delta 最大为 2。不能将这些补零当成额外的输入有效精度。

## 4. 两 lane 的指数 MAX 与控制

每个 lane 的两侧 e2 各 1 位，S2 形成 `p_lane`=e2A+e2B，范围 0…2。MXFP4/NVFP4 的 `p_lane`=0。`lane_active` 必须在 pair 抵消前，由八个非零乘积候选的 OR 得到；不得用 lane SOP 是否为零替代。

组级在 S2 对两路有效候选求 MAX，两个 lane 在同一边沿寄存 `r_group`。S3 使用 delta=`r_group`−`p_lane`；失活 lane 的移位控制取安全值。该路径是固定流水的组合侧带，没有独立握手，也没有组合反馈环；必须与同笔乘积、符号和格式同步。

S2 只需保存一份 lane 指数和及 group anchor，无需 8 份宽指数。S1 的 HiF4 e1 在解包后消耗，不再逐级传递；e2 在生成指数和后也无需保留原字段。独立符号一直用于 pair，S3/S4 恢复 TC；`all_negative` 的归约规则保持现有全部元素乘积符号定义，包括零元素。

同步高有效复位只清控制/有效位，无效周期数据寄存器保持。精简模式标志可用 `is_hif4`/`needs_mant_scale` 等内部表示，但接口可继续使用原 datatype 编码，并诊断不支持的请求。

## 5. 与当前 E 路径的数值对应

当前默认 `LOCAL_W`=28，S3 TC 叶子 29 位、S4 lane 31 位、S5 group TC 32 位。E 路径的每个 S3 叶子都含 17 个结构低零；HiF4 最大右移 2 位后仍有这 17 个零。候选移除这 17 位后，S3/S4/group 分别是 12/14/15 位，数值和符号不变。

~~~text
drop_local = LOCAL_W - 11              // 默认 17
leaf_base = leaf_E << drop_local
lane_base = lane_E << drop_local
group_base = group_E << drop_local
F_base = F_E + drop_local
~~~

这是对现有结构低零的精确压缩，不能直接推广为降低现有通用 lane 的 `LOCAL_W`。专用单元仍需与原 CModel/RTL 的 E 模式逐级验证，并与独立数学 reference 比较整体误差。

## 6. 进一步合并 HiF4 移位的备选

因为同 lane 八个乘积共享 delta，可将四个 pair 的精确移位移到求和之后：

~~~text
sum_i ((q_i * 4) / 2^delta) = (sum_i q_i * 4) / 2^delta
delta ∈ {0,1,2}
~~~

| 方案 | S3 | S4 | 取舍 |
| --- | --- | --- | --- |
| E0：建议首版 | 四个 pair、四个小移位 | 四路树 | 保持现有切点，易做等价验证 |
| E1：后续候选 | 八乘积规约为两个四项部分和 | 最终加法、一次 lane 移位 | 移位器减为一个，但需重分配树深并检查 S4 时序 |

等式成立依赖保护低零和 delta 范围；若采用 TC 算术右移，也必须先证明整除，不能把对负数的算术右移当作通用 RTZ。E1 不应简单把整棵树塞进 S3，先做静态时序后决定流水。当前讨论建议先 E0，再独立比较 E1。

## 7. 验证与待确认项

先确认保留三种 E 格式及 E0 切分；后续实施时增加专用 CModel/RTL，保留原多精度单元。覆盖所有元素编码乘积、HiF4 e1/e2 组合、两 lane 失活/抵消、正负零、逐拍换型、气泡和复位，检查上述各级压缩对应关系。G=1/2/4、全局窗口扫参和非法请求分别验收。

模块是否值得进一步折叠 HiF4 e1 或采用特制 4-bit 乘法逻辑，需由相同约束的面积/时序/活动功耗比较决定。首版使用直接无符号 4×4 乘法描述，交给 DC 映射，避免先引入复杂共享网络。
