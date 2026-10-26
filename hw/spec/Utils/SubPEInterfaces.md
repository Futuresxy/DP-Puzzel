# 解码字与固定点合同

对应源码：[SubPEInterfaces.scala](../../chisel_src/Utils/SubPEInterfaces.scala)。

SubPEInput携带独立A/B指数、尾数、符号和canonical product type。HQE/QE/E使用Valid结果及早anchor的基类。H/Q专用路径已经在各自PE中直接展开，不再使用SubPE接口或RawSubPEIO；其乘积寄存器直接属于PE。抽象基类不生成额外硬件层。

固定自然产品：FP16/BF16 UQ2.20 magnitude W22；Q UQ2.6 magnitude W8；FP4 signed lane W9，两级+&和为W11。SubPEConfig.forFamily只为保留的模块派生端口和载体：E=exp1/mant16/sign4，HQE/QE=10/16/4；H/Q在构造期拒绝，因为不存在对应SubPE模块。共享Q载体W=q_align_width+1，E W11；内部case class字段不额外暴露给脚本。

FixedLayout的I不含符号。SubPEProductAnchor在首次MAX前屏蔽零乘积，防止高指数零项污染对齐基准。数值位宽配置检查使用require；数据/valid复位由具体算术模块实现。本文件本身无流水。
