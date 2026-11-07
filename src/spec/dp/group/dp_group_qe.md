> 功能：定义 Q8E16 专用 group 和兼容 S5 token；范围：两个 QE lane、公共指数、组和、scale 与 LZD；版本：v1.7.0（待评审，未生效）；修改时间：2026-11-07 23:00:00 +08:00；对应代码：dp_group_qe 尚未实现；现有对照为 [dp_group.v](../../../verilog/group/dp_group.v)、[dp_scale_multiply.v](../../../verilog/arithmetic/dp_scale_multiply.v)、[dp_group_e.v](../../../verilog/group/dp_group_e.v)。

# Q8E16 专用 group 设计草案

`dp_group_qe` 由两个 [Q4E8 lane](../lane/dp_lane_qe.md) 组成，A/B 各 64 位；用于 [T8H16Q64E128](../dptop/mixed-precision-expansion.md) 的四个扩展组。它保留多精度 group 的 Q/E 数据流和 S5 到达拍，删除 T/H/INT8 能力。C 只在顶层处理，不进入本模块。

## 1. 流水与计算所有权

| 级 | lane 拥有 | group 拥有 |
| --- | --- | --- |
| S1 | 两侧元素紧凑解包 | 两侧 scale 解包；HiF4 e1/e2 分发 |
| S2 | 4×4 元素乘法、指数和、lane MAX | 两 lane MAX→共同 r；scale 4×4 系数积与指数和 |
| S3 | Q RTZ 或 E pair/小移位、符号恢复 | 使能传递 scale、类型、特殊值 |
| S4 | 四叶平衡树，保存 lane 和 | 继续传递 scale 旁带 |
| S5 | 提供两路 S4 和 | 两 lane TC 相加→abs→NV/HiF scale→LZD；融合 anchor/特殊值，注册 token |

S2 的共同 r 同拍返回两 lane；不是 group 与 lane 的独立流控。S5 仍包含组加法、abs、14×8 乘法和 LZD，不能因裁剪模式就宣称此级时序必然通过。默认 28/40，L8/II=1 的整体边界与现有顶层一致。

## 2. scale 与参数化位宽

使用 [scale 公共合同](scale.md)：Q/MXFP4 的 E8M0 只改变指数，NVFP4 的 E4M3、HiF4 的 E6M2 为非负 scale；scale 非法/特殊分类沿用现有语义。两侧解包系数各 4 位 I1F3，S2 系数积 8 位 I2F6。只对 NV/HiF 进入 S5 数据乘法，Q/MX 直接旁路。

定义 `P=LOCAL_W-2`，`LANE_SUM_W=LOCAL_W+3`，`GROUP_SUM_W=LOCAL_W+4`，`GROUP_MAG_W=LOCAL_W+3`。默认分别为 31、32、31 位。NV/HiF 从组和幅值精确去掉 `GROUP_SUM_W-15=LOCAL_W-11` 个结构低零，得到 14 位幅值；乘以 8 位 scale 系数，完整保存 22 位无符号乘积，再低补 `GROUP_MAG_W-22=LOCAL_W-19` 位。符号独立传递，不引入 15×9 有符号乘法。

| 节点 | 精度 | 表示 | S | I | F | 数值位宽 |
| --- | --- | --- | ---: | ---: | --- | --- |
| S5 两 lane 组和 | Q | TC | 1 | 5 | P | LOCAL_W+4 |
| S5 两 lane 组和 | MXFP4/NVFP4 | TC | 1 | 10 | P−5 | LOCAL_W+4 |
| S5 两 lane 组和 | HiF4 | TC | 1 | 8 | P−3 | LOCAL_W+4 |
| 紧凑 scale 数据输入 | NVFP4 | unsigned | 0 | 10 | 4 | 14 |
| 紧凑 scale 数据输入 | HiF4 | unsigned | 0 | 8 | 6 | 14 |
| scale 系数输入 | NVFP4/HiF4 | unsigned | 0 | 2 | 6 | 8 |
| scale 乘积 | NVFP4 | unsigned | 0 | 12 | 10 | 22 |
| scale 乘积 | HiF4 | unsigned | 0 | 10 | 12 | 22 |
| S5 token 数值 | Q | SM | 1 | 5 | P | LOCAL_W+4 |
| S5 token 数值 | MXFP4 | SM | 1 | 10 | P−5 | LOCAL_W+4 |
| S5 token 数值 | NVFP4 | SM | 1 | 12 | P−7 | LOCAL_W+4 |
| S5 token 数值 | HiF4 | SM | 1 | 10 | P−5 | LOCAL_W+4 |

表中 SM 总宽包括独立符号，`out_magnitude` 本身只有 `GROUP_MAG_W` 位。低补零属于精确坐标转换，不产生新的有效精度。合法参数继续要求 `LOCAL_W>=27`、`GLOBAL_W>=max(LOCAL_W+4,33)`；默认 28/40。改变窗口后必须同时生成树宽、补零、anchor/z 字段和测试配置。

## 3. 与现有 group 相同的 S5 接口

| 字段 | 默认宽度 | 合同 |
| --- | ---: | --- |
| `out_valid` | 1 | 输入在 n 接收，S5 于 n+4 更新；气泡仍推进 |
| `out_negative` | 1 | 独立符号；包括原有负零语义 |
| `out_magnitude` | 31 | 未做动态规格化的无符号幅值 |
| `out_anchor` | signed 10 | 原幅值最高物理位的指数 A_raw |
| `out_z` | 5 | 对原幅值的 LZD 计数；零/特殊值按原合同屏蔽 |
| `out_special` | 4 | 与原 group 相同的分类位定义 |

对非零有限源，必须满足：

```text
value = (-1)^negative * magnitude * 2^(A_raw-(GROUP_MAG_W-1))
effective_exponent = A_raw - z
```

设 `alpha_scale=scale_E_a+scale_E_b-254`，r 为本组公共元素指数和：

| 精度 | alpha（施加 scale 后） | A_raw | 默认输出 F |
| --- | --- | --- | ---: |
| Q | r−30+alpha_scale | r+alpha_scale−26 | 26 |
| MXFP4 | alpha_scale | alpha_scale+9 | 21 |
| NVFP4 | alpha_scale | alpha_scale+11 | 19 |
| HiF4 | r+alpha_scale | r+alpha_scale+9 | 21 |

上述偏移来自 `A_raw=alpha-F+(GROUP_MAG_W-1)`，不能在 S6 按 datatype 再扣一次 F。Q 的 anchor 范围仍需要 signed10；局部 r 缩成 U6，不意味着全局 anchor 也可缩成 6 位。

**QE 与多精度 group 在 Q/E 下采用同坐标，应逐字段 bit-exact 对照。** 既有 E-only group 的 HiF4 已在 lane 内融合 e2，因此其 magnitude/A_raw/z 可与多精度不同；它按 [E group 第 4 节](dp_group_E.md#4-与原多精度-group-对齐的输出-layout) 的坐标变换保持相同数值和 S6 对齐结果。这两种“兼容”不能混为所有内部位都相等。

## 4. 屏蔽与特殊结果

顶层只在当前请求支持 Q/E 时给扩展组有效输入；本组 valid 每拍推进，数据 DFFE 在无效时保持。对无效周期不得使用其保留 token 参与 MAX、特殊值归约或负零归约；最终屏蔽属于顶层职责，不能假设 group 无效时数据一定为零。

组内保持原配对分类、scale 分类、正负 Inf 冲突与 all-negative 语义。零的符号不能直接由 TC 和的符号位生成；非零项抵消与全部负零是不同情况。MX/Q 时隔离 NV/HiF 数据乘法输入，不新增生成时钟。

## 5. 实现和验收边界

拟新增 `src/verilog/group/dp_group_qe.v` 与对应 CModel group/lane 能力实现，公共 token、scale 和顶层后端各保留一份定义。CModel 可复用共享 Q/E 算术，但 trace 必须对应 QE 的窄乘积和实际阶段，不能把未来 RTL 当作已存在。

评审后实施时，对相同两 lane 输入逐级对照原多精度 group 的全部七个 Q/E 子型，检查 S2 公共 r、S4 lane 和、S5 全部字段。测试还须覆盖两 lane 指数差、scale 边界/特殊值、符号抵消、Q/E 换型、气泡、复位和窗口变体。后续 DC 单独报告 QE 前端与整 DP，不用元素乘法器数量推算面积百分比。
