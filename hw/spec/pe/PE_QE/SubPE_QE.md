# SubPE_QE：QE 专用通路

对应源码：[SubPE_QE.scala](../../../chisel_src/pe/PE_QE/SubPE_QE.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

四个4×4资源随Q/E互斥使用，Q两lane先MAX，仅MIN按q_align_width窗口RTZ，E四lane两级和；紧凑操作数寄存与末级CPA共享。结果W=q_align_width+1，Q的I3，E I8/Hi I6，F=W−1−I。早anchor1拍、结果3拍、II1。

Valid-only，valid复位0，payload RegEnable保持不复位；无隐式宽度舍入。所有格式特值由解包sideband处理，不能只检查numeric占位。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
