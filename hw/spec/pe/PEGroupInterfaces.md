# PEGroupInterfaces.scala：组级 Bundle 与接口外壳

对应源码：[PEGroupInterfaces.scala](../../chisel_src/pe/PEGroupInterfaces.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

`PEGroupInput` 聚合独立 A/B VectorInputBundle；Full shape 为4 word、1 scale、4 g0、2 g1。PEGroupOutput 是 signed W33 mul_scale_mant 和特殊值 flags；PEGroupAnchor 是 W11 signed raw anchor。二者分别在 S07 与 S06 发布，不能把它们当同拍原子输出。

抽象 PEGroupBase 只定义 IO/shape，不产生额外 RTL 计算层。检查 scale=1、g0=dimk 且为偶数、g1=g0/2、outputWidth>0；Full 子类固定 dimk4。内部全部 Valid，去掉原工程永远不影响计算的 ready，故无反压/stall。

Bundle 无自身延迟/寄存器/复位；相关控制/valid 的7拍合同由 PEGroupFull 负责。尚留私有 shift 配置 Bundle 作为原源接口元信息，不是额外实例或可调参数。待结构检查接口宽度，待 SV 验证早 anchor 与晚数据严格一拍配对。
