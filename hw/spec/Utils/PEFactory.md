# 六种PE的生成选择

对应源码：[PEFactory.scala](../../chisel_src/Utils/PEFactory.scala)。

按PEConfig族选择PE_H/PE_Q/PE_E/PE_HQE/PE_QE，E把g2/g4作为构造参数传入。generator仅new用于ChiselStage顶层；instantiate在父Module里调用Module(generator)。这是elaboration时选择，不生成六套电路再加输出MUX。

所有返回类有同一PEBase接口，但端口长度按profile wordCount派生；alignment显式传递同一不可变值。非法profile在PEConfig拒绝。无本身Module/状态/周期，实例边界在所选具体PE中保持可追溯。
