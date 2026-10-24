# PE_QE：QE 专用通路

对应源码：[PE_QE.scala](../../../chisel_src/pe/PE_QE/PE_QE.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

合法profile为 PE_QE_g4。统一输出sign/magnitude/top_anchor/zero/special，F=pe_align_width、总W=F+2；输入cfg必须保持至排空，II1、S11输出，控制/valid复位、数据有效更新不复位。

保留源工程字内/PG/PE分级组织，PE跨PG使用PEAlignNormalize。四PG自然和增长2位，S11规范化无损；已有RTZ误差不会被恢复。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
