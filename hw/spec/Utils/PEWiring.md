# PE的公共切片与连接

对应源码：[PEWiring.scala](../../chisel_src/Utils/PEWiring.scala)。

纯Scala装配函数，无寄存器或额外Module。connectInputs按每四word切分A/B和HiF4 bits，独立选择两侧scale。MXFP8/6和HiF4为slot0；MXFP4为0/0/1/1；NV为0/1/2/3。g2取其前两组，即MXFP4 slot0、NV slot0/1；HiF4主scale须由映射层复制并切分组位。

supported由族能力、A/B配对与data/scale共同判断，有效非法输入断言。connectInput适配分级PG；H/Q原始乘积PG使用同一输入函数。connectResults只用于分级PG早anchor/晚data与公共规约，输出同一个PEDotResult。连接不会改变算术或延迟。
