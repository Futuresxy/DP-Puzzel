# PEGroup_H：H 专用通路

对应源码：[PEGroup_H.scala](../../../chisel_src/pe/PE_H/PEGroup_H.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

每组四个SubPE_H输出4个W22高精度产品，合并special，S02 Valid原子输出。没有PG MAX、移位或局部和，不再使用分级PG的早anchor/晚data协议。H不计算scale。 valid复位，数据保持，II1。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
