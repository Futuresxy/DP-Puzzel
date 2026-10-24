# SubPE_H：H 专用通路

对应源码：[SubPE_H.scala](../../../chisel_src/pe/PE_H/SubPE_H.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

FP16/BF16统一到UQ1.10，一个11×11乘法得到W22 UQ2.20 magnitude；独立sign，top_anchor=rawExpSum−2*bias+1。输入S01，一拍S02输出，没有局部对齐/求和，零使用-1024anchor。

Valid-only，valid复位0，payload RegEnable保持不复位；无隐式宽度舍入。所有格式特值由解包sideband处理，不能只检查numeric占位。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
