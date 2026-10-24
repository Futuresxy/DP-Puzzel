# 解码字与固定点合同

对应源码：[SubPEInterfaces.scala](../../chisel_src/Utils/SubPEInterfaces.scala)。

SubPEInput携带独立A/B指数、尾数、符号和canonical product type。HQE/QE/E使用Valid结果及早anchor的基类；H/Q使用RawSubPEIO输出独立未对齐乘积。抽象基类不生成额外硬件层。

固定自然产品：FP16/BF16 UQ2.20 magnitude W22；Q UQ2.6 magnitude W8；FP4 signed lane W9，两级+&和为W11。SubPEConfig.forFamily集中派生实际端口和载体：H=exp8/mant12/sign1；Q=10/12/2；E=1/16/4；HQE/QE=10/16/4。共享Q载体W=q_align_width+1，E W11；内部case class字段不额外暴露给脚本。

FixedLayout的I不含符号。SubPEProductAnchor在首次MAX前屏蔽零乘积，防止高指数零项污染对齐基准。数值位宽配置检查使用require；数据/valid复位由具体算术模块实现。本文件本身无流水。
