> 功能：定义 Q4E8 专用 lane 的候选计算通路；范围：紧凑解包、4×4 乘法、局部对齐及 S1–S4；版本：v1.7.0（已批准，分阶段实施）；修改时间：2026-11-07 23:00:00 +08:00；对应代码：[QE CModel](../../../cmodel/lib/lane/lane_qe.cpp) 已实现；dp_lane_qe RTL 待实施；现有对照为 [dp_lane.v](../../../verilog/lane/dp_lane.v)、[dp_lane_unpack.v](../../../verilog/unpack/dp_lane_unpack.v)、[dp_lane_e.v](../../../verilog/lane/dp_lane_e.v)。

# Q4E8 专用 lane 设计草案

本稿配合 [Q8E16 group](../group/dp_group_qe.md) 和 [三种混合 DP](../dptop/mixed-precision-expansion.md) 评审。拟新增 `src/verilog/lane/dp_lane_qe.v`，裁剪多精度 lane 中的 T/H/INT8 运算，不修改既有 `dp_lane` 和 `dp_lane_e` 的功能。本轮已按用户授权建立 QE CModel；RTL 与 PPA 在模型验证后实施。

## 1. 能力与复用边界

| 类别 | 支持精度 | 每 lane 点积项数 | A/B 各自输入宽度 |
| --- | --- | ---: | ---: |
| Q | MXFP8 E4M3、E5M2；MXFP6 E3M2、E2M3 | 4 | 32 |
| E | MXFP4、NVFP4、HiF4 | 8 | 32 |

A/B 必须同格式。INT8 虽同样按字节存放，仍不属于 QE 能力集；它只由混合顶层的原四组计算。Q 的 scale 为 E8M0；E 的 scale 规则由 group 管理。FP6 的项目输入仍占 8 位槽，编码放高 6 位、低 2 位为零。

复用 [元素数值解包](unpack.md)、[特殊值](../common/special-values.md)、[共享移位语义](shifter-sharing.md) 和公共 DFF/算术基础单元。QE 专用入口只生成 Q/E 字段选择与算术；不能实例化完整多精度 lane 后仅屏蔽输出，并把它算作资源裁剪。

建议模块边界为 QE 解包、QE 尾数 bank、QE 指数 bank、局部对齐、四叶加法树。解包可做专用包装或静态能力裁剪，具体源文件拆分在实现时确定；必须能从 elaboration/综合网表确认 T/H/INT8 数据通路被删除。公共格式译码和算术应复用，避免另写一套数值定义。

## 2. 保持多精度 Q/E 的流水切分

| 级 | 组合计算 | 本级保存 | 与现有多精度 Q/E 的关系 |
| --- | --- | --- | --- |
| S1 | A/B 紧凑解包；Q 重编码，HiF4 e1 融合；元素分类 | M32/E20/S8 及必要分类；HiF4 e2；类型/valid | 同字段语义，不引入 184 位展开记录 |
| S2 | unsigned 4×4 乘法、sign XOR、Q 指数和；lane MAX→group MAX；配对特殊值归约 | 8×8 位幅值槽、sign、活动槽、指数、共同 r、特殊摘要 | Q 用 4 槽，E 用 8 槽；去掉原 22 位乘积槽的无用高位 |
| S3 | Q 幅值 RTZ；E 先做四个 signed pair，再取幅值、小移位和符号恢复 | 四路 `LOCAL_W+1` 位 TC 叶子，r/类型/特殊摘要 | 与多精度相同的截断点 |
| S4 | 四叶平衡加法树 | 一路 `LOCAL_W+3` 位 TC lane 和，r/特殊摘要 | 删除 T/H 输出低补零选择；同拍交给 group |

本方案有意保留 QE 与多精度 Q/E 相同的 S2/S3 边界。已有 E-only 的 S2 pair、S3 窄树、S4 左移是另一种前端；QE 首版不混用两套切分，也不把 HiF4 e2 提前融合到 QE 乘积。三类 group 的外部到达时刻统一为 S5。

输入在边沿 n 接收并保存 S1，S4 在 n+3 更新；组合结果以所属目标级命名。流水寄存值采用 `r1_a_mantissas`、`r2_product_magnitudes`、`r3_aligned_terms`、`r4_lane_sum` 等功能名；禁止仅用 a/e/f 或 valid 向量下标隐含流水级。

## 3. 紧凑字段与特殊值

每侧两个 16 位输入原子块，各输出 M16/E10/S4。同一字段容器按模式取位：Q 每原子块两个 M4 和两个 E5；E 四个 M4、四个符号，MX/NV 无元素指数，HiF4 保留 lane 的 e2。只在 bank 输入端按模式选择对应字段，闲置位固定为零，不先扩为最大格式再拆开。

Q 使用统一的 I1F3 幅值和有效偏置指数 E5；E2M1 转为 I3F1；HiF4 e1 融合后为 I2F2。具体 bit-field 沿用共享解包布局，新增布局必须以具名宏/派生宽度描述。S2 对外使用紧凑的逻辑顺序：Q 槽 0–3 有效、4–7 为零；E 槽 0–7 有效。物理乘法器到逻辑槽的映射需要显式连线。

分类在解包边界完成：Q 的 NaN/Inf、零、非正规处理沿用原定义；A/B 配对处理 0×Inf、NaN、正/负 Inf。E 元素本身有限，但 scale 的特殊值由 group 合并。不能把“幅值为零”和“槽不参与”合并为同一个标志；负零需要原始乘积符号的归约结果，不能用求和后的符号替代。

## 4. 乘法与指数资源

每 lane 配置 8 个 unsigned 4×4 乘法器：Q 激活其中四个，E 激活八个。移除 T/FP16 的 11×11 重构、BF16 宽乘法路由、INT8 幅值/乘法路径及相应宽 MUX。Q 的四个 E5+E5 相加结果为 U6；HiF4 的 e2_a+e2_b 为 U2；MX/NV 为常量零。共同 r 使用 U6 足够覆盖 QE，有限 Q 最大值为 60。

S2 中，两 lane 各自产生有限非零候选 `(has_value, exponent_max)`，group 同拍比较后返回共同 r。没有新增握手或寄存级；lane 候选不能依赖返回 r，以免形成组合环。若全组无有限非零乘积，则 r=0 并携带空标志，特殊结果另走旁带。

每 lane 保留四路局部幅值移位器。Q 按共同 r 对齐；HiF4 只有两 lane 的 e2 和差 0/1/2；MX/NV 无动态移位。Q 模式下关闭空乘积槽及 E pair 专属输入，E 模式下隔离 Q 指数算术。寄存保持只能减少切换，实际功耗下降仍需活动仿真确认。

## 5. 乘积、树与移位的 S/I/F

定义 `P=LOCAL_W-2`；S 不计入 I；TC 为二补码，SM 为独立符号加幅值。表中乘法器的 unsigned 行不含独立符号线。默认 `LOCAL_W=28`，P=26。外部二进制指数另行携带，F 不是总的数学精度保证。

| 节点 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | ---: | ---: | --- | --- |
| S1 元素 | Q | SM | 1 | 1 | 3 | 5 |
| S1 元素 | MXFP4/NVFP4 | SM | 1 | 3 | 1 | 5 |
| S1 元素 | HiF4 | SM | 1 | 2 | 2 | 5 |
| S2 单乘积 | Q | unsigned | 0 | 2 | 6 | 8 |
| S2 单乘积 | MXFP4/NVFP4 | unsigned | 0 | 6 | 2 | 8 |
| S2 单乘积 | HiF4 | unsigned | 0 | 4 | 4 | 8 |
| S3 pair 输入 | MXFP4/NVFP4 | TC | 1 | 6 | 2 | 9 |
| S3 pair 输入 | HiF4 | TC | 1 | 4 | 4 | 9 |
| S3 pair 输出 | MXFP4/NVFP4 | TC | 1 | 7 | 2 | 10 |
| S3 pair 输出 | HiF4 | TC | 1 | 5 | 4 | 10 |
| S3 对齐叶子 | Q | TC | 1 | 2 | P | LOCAL_W+1 |
| S3 对齐叶子 | MXFP4/NVFP4 | TC | 1 | 7 | P−5 | LOCAL_W+1 |
| S3 对齐叶子 | HiF4 | TC | 1 | 5 | P−3 | LOCAL_W+1 |
| S4 lane 树输出 | Q | TC | 1 | 4 | P | LOCAL_W+3 |
| S4 lane 树输出 | MXFP4/NVFP4 | TC | 1 | 9 | P−5 | LOCAL_W+3 |
| S4 lane 树输出 | HiF4 | TC | 1 | 7 | P−3 | LOCAL_W+3 |

Q 的 W8 幅值低补 `LOCAL_W-8` 位后进入局部 RTZ。E pair 的 W10 TC 先分离符号，W9 幅值低补 `LOCAL_W-9` 位；其中至少两位为 HiF4 小移位预留。移位后恢复 TC，再做两层平衡加法，增长两位。S3 只采用幅值右移，不能用负数算术右移替代 RTZ。

## 6. 复位、接口和验收

`clock`、同步低有效 `rst_n`、无背压、II=1；valid 每拍推进，payload 仅在该级有效时写入 DFFE；DFF 紧随本级计算。数据/符号/类型/指数/特殊摘要必须属于同一请求。上层只向 QE 发合法 Q/E 请求，非法直接调用也必须被诊断，不能解释成某个默认格式。

实施后至少检查：七个子型、所有特殊分类、局部指数边界、HiF4 两 lane 的 e2 差、正负抵消与负零；Q/E 每拍切换、气泡、复位取消；合法 LOCAL_W 变体。与多精度 lane 对照 S1 有效字段、S2 乘积/指数/特殊摘要、S3 四叶和 S4 lane 和；未使用物理位不强求相同。独立数学 golden 负责误差度量，不能替代这些 bit-exact 断点。
