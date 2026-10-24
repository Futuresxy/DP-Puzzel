# 六种PE的统一输出

对应源码：[PEInterfaces.scala](../../chisel_src/Utils/PEInterfaces.scala)。

PEBase仅提供shape、alignment和IO。PEIO输入是packed向量+稳定cfg，输出原子Valid PEDotResult：magnitude W(F+1)、negative、top_anchor W11、is_zero、special，F=pe_align_width，所有六种profile一致。

物理值=(-1)^negative*magnitude*2^(top_anchor-F)，非零最高1在bitF，zero数值为0且anchor=-1024。PE内部可使用不同自然宽度，但输出必须显式转换，不能隐式truncate。PEMath只做有依据的符号扩展/精确placement/scale slot计算；无隐藏寄存。

g4默认F40/总W42；g2内部规范化F39后补一个低0达到相同F40，保持sign和normalized anchor。cfg必须保持至排空；输出不带C，不做FP32舍入，无反压。11级周期由具体PE实现并验收。
