# 原子格式解码函数

对应源码：[DecodePrimitives.scala](../../chisel_src/Utils/DecodePrimitives.scala)。

共享单元素FP16/BF16、FP8/6、E2M1、源HiF4解码和classify，以及scale原子解码；只在HQE/QE/E的DataUnpack调用处生成组合电路，无独立Module/状态。专用H/Q已把各自格式转换直接展开在PE文件；H使用unit，Q只解E8M0指数和NaN。

FP16解码尾数含一个低padding0；BF16为hidden+7fraction；Q为统一E5指数和4bit尾数，高lane放nibble2；E2M1指数融合进4bit尾数。特殊值数值占位与sideband并行。HiF4使用源E6M2 bias48、g0/g1实验语义，外部规范待确认。所有转换仍需完整独立数值验证。
