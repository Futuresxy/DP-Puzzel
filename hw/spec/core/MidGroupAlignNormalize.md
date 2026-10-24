# MidGroupAlignNormalize.scala：四组对齐与规格化辅助

对应源码：[MidGroupAlignNormalize.scala](../../chisel_src/core/MidGroupAlignNormalize.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

Full调用固定四路、groupDataWidth33、alignWidth40..64。PG anchor/data分别S06/S07到达，所有anchor有效位须相同；S07注册MAX/index，data有效必须匹配这个寄存valid。全零哨兵−1024转换为安全内部基准0，防止加负offset越界。

S08将PG W33补低零到alignWidth，MAX旁路，其余三个signed RTZ对齐；floor与correction分别寄存。rawTop=selectedAnchor+topAnchorOffset+2，offset由稳定cfg计算并显式输入；先加宽到anchorWidth+2再断言可截回W11。S09带修正CSA得到alignWidth+2和；S10/S11经MidGroupNormalizeExact无损规格化。

in_anchors与in_groups都是Valid，故无独立反压或等待队列；整个辅助从早anchor到输出有5个边界，对PG数据为4个，整体MidGroup为11拍。valid同步复位，data保持不复位。输出统一原子sign/magnitude/anchor/zero/special，默认W42/F40。

源代码保留2路参数分支，Full-only入口只用4。待SV验证anchor/data错拍断言、全零、RTZ correction、cfg稳定、严重抵消和W64。它是MidGroup内部算术辅助，不构成新的dot组织层。
