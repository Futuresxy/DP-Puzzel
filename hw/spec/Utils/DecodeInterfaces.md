# 解包数据与分类接口

对应源码：[DecodeInterfaces.scala](../../chisel_src/Utils/DecodeInterfaces.scala)。

按族cfg位宽参数化的指数/尾数/符号/逐lane分类Bundle，A/B各自一份；PG消费合并special而不储存逐lane分类向量。scale指数W8 bias127、尾数W4 UQ1.3，unit为8。

DataUnpackBase只有packed输入和Valid解码输出，属于IO外壳，不产生额外module。专用DataUnpack各自决定固定S01寄存位置；接口无ready。位宽和lane个数由内部族合同派生，不能以截断隐藏unsupported格式。
