# SubPE_Q：Q 专用通路

对应源码：[SubPE_Q.scala](../../../chisel_src/pe/PE_Q/SubPE_Q.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

两个4×4产生W8 UQ2.6独立乘积，Q高lane仍在nibble2、sign1；top_anchor=E5重偏后的rawExpSum−29。一拍S02输出，无字内MAX/RTZ，E8M0块指数在PE层统一附加。

Valid-only，valid复位0，payload RegEnable保持不复位；无隐式宽度舍入。所有格式特值由解包sideband处理，不能只检查numeric占位。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
