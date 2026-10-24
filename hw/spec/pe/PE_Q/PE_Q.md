# PE_Q：Q 专用通路

对应源码：[PE_Q.scala](../../../chisel_src/pe/PE_Q/PE_Q.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

合法profile为 PE_Q_g4。统一输出sign/magnitude/top_anchor/zero/special，F=pe_align_width、总W=F+2；输入cfg必须保持至排空，II1、S11输出，控制/valid复位、数据有效更新不复位。

四个PEGroup_Q只是产品簇，32个产品统一MAX/对齐。S03 MAX、S04 deltas、S05 RTZ、S06–S09自然位宽树、S10/11规范化；最后显式RTZ到公共输出窗。Q的E8M0 block指数只计算一次，不存在scale尾数乘法。 字内/PG局部对齐已删除。该数值合同与分级共享通路不同，不能用相同F宣称同等误差。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
