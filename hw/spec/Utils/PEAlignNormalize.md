# HQE/QE/E的分级规约与g2坐标扩展

对应源码：[PEAlignNormalize.scala](../../chisel_src/Utils/PEAlignNormalize.scala)。

保留原工程算法：PG anchor S06、data S07；S07 MAX，S08精确placement后N−1 RTZ对齐，S09 CSA含负数floor修正，S10/S11无损规范化。groupCount只允许2/4，输入为族PG合同载体，窗口A=pe_align_width；自然sum W=A+ceil(log2(g))。

公共输出W=A+2、F=A。g4内部W=A+2/F=A，直接输出；g2内部W=A+1/F=A−1，在规格化后的magnitude低端Cat一个0，保持normalized anchor/sign，value恒等。运行期assert g2有效输出LSB=0。不能把g4的raw anchor +2规则用于g2：内部raw anchor按实际carryBits +1/+2增长。

zero哨兵不参与非零MAX，全部零用安全内部基准0；special独立merge。Valid-only、固定11级PE合同、II1，valid复位0、payload有效使能不复位。需要验证极端scale、严重抵消、RTZ、zero哨兵及g2/g4坐标，定向smoke不覆盖全部情况。
