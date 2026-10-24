# H/Q未对齐乘积集合

对应源码：[RawProductInterfaces.scala](../../chisel_src/Utils/RawProductInterfaces.scala)。

RawProducts将每lane的自然magnitude、negative、top_anchor W11、is_zero及group special组成原子Valid集合。top_anchor表示magnitude最高物理位的指数，不要求该位已经是1。H每word一个W22产品，Q每word两个W8产品；PG聚合4word，分别4/8lane。

RawSubPEIO输入仍是各族解码SubPEInput；RawGroupIO是四word输入和产品集合输出，不发布原分级PG的S06/S07双通道。Bundle不产生寄存，具体SubPE/PG在S02提供一拍产品valid。零必须屏蔽anchor，否则全局MAX会误丢非零项。
