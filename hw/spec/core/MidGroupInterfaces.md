# MidGroupInterfaces.scala：中层结果与构造边界

对应源码：[MidGroupInterfaces.scala](../../chisel_src/core/MidGroupInterfaces.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

PETileMath 提供resizeSInt、精确MSB放置、格式兼容转发和localScaleIndex。精确放置只允许srcWidth≤dstWidth，通过追加低零扩大F；clearLowBitsTowardZero是源遗留未使用函数，不是本轮配置开放的精度旋钮。

MidGroupContract固定4个PG、anchorW11、carry2。MidGroupOutput 默认总W42，独立W41 magnitude/sign、W11 anchor、zero和special。物理值 `(-1)^sign×magnitude×2^(anchor−(W−2))`；这是完整原子Valid token。

MidGroupBase是IO/shape抽象外壳，不产生额外实例。Full子类使用4组、16 word/4 scale/16 g0/8 g1；alignWidth显式构造，输出W=alignWidth+2。保留源2组接口可能性但Full配置从不选择它。cfg是稳定batch控制，输入输出Valid、无ready。

本文件没有数据寄存/额外延迟/复位逻辑，MidGroupFull负责11拍。待SV检查同一token内sign/magnitude/anchor/zero/special的同步、scale slot和精确placement；不能只验证字段名。
