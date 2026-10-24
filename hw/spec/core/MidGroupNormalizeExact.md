# MidGroupNormalizeExact.scala：无损两拍规格化

对应源码：[MidGroupNormalizeExact.scala](../../chisel_src/core/MidGroupNormalizeExact.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

输入signed W位R、raw_top_anchor W11和special，值为R×2^(Araw−(W−2))。firstStage只决定信号标签，默认10，不改变电路延迟。参数要求W和anchorWidth≥3。

第一拍把R扩成W+1取abs，证明高位无溢出，保留W位magnitude并计算LZC。第二拍对普通值左移LZC−1，使最高1落到W−2；最小负数abs=2^(W−1)时精确右移1并把anchor加1。统一Aout=Araw+1−LZC，对非零断言W11不溢出。零输出magnitude0、sign0、is_zero1和最小anchor哨兵，special独立传播。

输出magnitude W−1与独立sign，S1/I1/F(W−2)，规格化不丢位。Valid-only延迟2、II1，valid复位0，data无复位/仅有效使能。没有ready、sticky或舍入。

待SV覆盖所有one-hot、最小负数、±1、零、符号与指数一致、各合法W以及复位/气泡；“无损”是算法合同，数值回归尚未执行。
