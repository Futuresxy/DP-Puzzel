# SubPE_E：E 专用通路

对应源码：[SubPE_E.scala](../../../chisel_src/pe/PE_E/SubPE_E.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

四个4×4得到8bit无符号产品，施符号为W9，两级+&自然增长W10/W11；不舍入。S02产品、S03 pair、S04最终局部和。元素E2M1/NV为S1/I8/F2，HiF4为S1/I6/F4，PG拥有anchor，此leaf早anchor端口固定无效。

Valid-only，valid复位0，payload RegEnable保持不复位；无隐式宽度舍入。所有格式特值由解包sideband处理，不能只检查numeric占位。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
