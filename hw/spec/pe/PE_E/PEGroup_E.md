# PEGroup_E：E 专用通路

对应源码：[PEGroup_E.scala](../../../chisel_src/pe/PE_E/PEGroup_E.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

每组4个SubPE；S01解包、S02乘积/scale、S03 MAX、S04移位控制、S05对齐、S06局部和/zero-masked anchor、S07数据。anchor/data间距1，Valid-only、II1，data有效使能不复位。

E保留同anchor预加、单个小移位器与scale乘法：SubPE W11→pair12→加group_guard_bits→最终局部和，再乘signed(scaleProduct W8+符号1)自然增长。输出丢2个经证明的结构零位，W=20+group_guard_bits（默认22）。MX/NV坐标I13，HiF4 I11；raw-to-top偏移分别12/10。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
