# PEGroup_HQE：HQE 专用通路

对应源码：[PEGroup_HQE.scala](../../../chisel_src/pe/PE_HQE/PEGroup_HQE.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

每组4个SubPE；S01解包、S02乘积/scale、S03 MAX、S04移位控制、S05对齐、S06局部和/zero-masked anchor、S07数据。anchor/data间距1，Valid-only、II1，data有效使能不复位。

载体W=(q_align_width+1)+group_guard_bits+2，默认33；MAX旁路、其他三项RTZ修正并入CSA，NV/HiF4走紧凑scale-tail乘法，unit scale旁路。H/Q/E整数位分别按4/5/10（NV13/Hi11）转换raw anchor；未开启H的QE不接受高精度。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
