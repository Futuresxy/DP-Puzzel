> 功能：Q4 专用 lane；范围：四种 MXFP8/6 的 S1–S4、S2 公共 MAX 接口；版本：v1.10；修改时间：2026-11-12 18:50:00 +0800；对应代码：src/verilog/lane/dp_lane_q.v、src/verilog/unpack/dp_operand_unpack_q.v、src/cmodel/lib/lane/lane_q.cpp；Chisel 未实现。

# Q4 专用 lane

`dp_lane_q` 只接受 MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3。每个 A/B 输入容器为 32 bit，含四个字节槽；FP6 使用各字节高六位，低二位必须为零。不存在 E pair、HiF e1/e2、T/H/INT 或精度复用乘法分支。Q 数值与当前 QE 的 Q 路径一致。

输入 `in_valid` 与合法 Q datatype 共同启动；非法类型形成气泡。没有独立 ready 或反压。`clock` 上升沿捕获，`rst_n` 同步低有效。valid 每拍推进，payload 用无复位带使能 DFF。连续不同 Q 类型请求可每拍接收；无效期间保持数据。

| 阶段 | 计算与保存 | 默认数值格式 |
| --- | --- | --- |
| S1 | 四个独立 Q 解包，A/B 分类按元素配对，保存乘积符号、有限非零位、special、全负摘要 | 每侧 4×U4 幅值（I1F3）及 4×U5 指数（bias15） |
| S2 | 四个 4×4 无符号乘法；指数相加及有限非零 MAX；接收 group 返回的公共 MAX | 4×U8 乘积（I2F6）、4×U6 指数和、公共 U6 MAX |
| S3 | 乘积低补 LOCAL_W−8 个零；以公共 MAX 减本项指数，幅值 RTZ 后恢复符号 | 4×S29（I2F26，符号独立计1位） |
| S4 | 平衡四项加法树，完整保存两位增长 | S31（I4F26） |

LOCAL_W 默认28，合法下界27；`LEAF_W=LOCAL_W+1`，`LANE_SOP_W=LOCAL_W+3`。S3 正负数均对无符号幅值右移后再恢复补码，避免负数算术右移造成向负无穷舍入。移位量大于等于窗口时返回零，不截断移位量取模。

`out_candidate`/`out_candidate_active` 是 S2 组合接口，来自 S1 指数与分类，与乘法并行；group 合并两个 lane 的候选后返回 `in_group_max`，同拍进入 S2 寄存器。这个依赖不跨请求，也不依赖 S4 的输出，不形成组合环。有限零和 NaN/Inf 不参与 MAX。

S4 输出接口与 QE lane 的 Q 路径兼容：`out_valid`、有符号 `out_sop`、公共 `out_anchor`（此处仍是 bias15 的乘积指数和 U6）、`out_special` 和 `out_all_negative`。特殊值按原始成对元素归约，包括 0×Inf、sNaN、正负 Inf 冲突；全负摘要包含零项乘积符号，不能从最终和的符号反推。

本模块不做 scale，scale 在 group 中只以 E8M0 指数参与坐标。验收使用新增完整顶层冻结 RTL 的四种 Q64 原生数据、S3/S4/S5 断点及门控保持检查，见 [Q 扩展顶层](../dptop/t8h16q64e64.md)。
