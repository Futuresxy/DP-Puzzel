# CUnpacker.scala：C 解码与精确规格化

对应源码：[CUnpacker.scala](../../chisel_src/core/CUnpacker.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

C在PETile中先延迟9拍，本模块两拍将FP32或低16bit FP16/BF16转为独立magnitudeW24/sign、anchorW11，坐标S1/I1/F23。第一拍按cfg C type解码，subnormal指数用1−bias，尾数hidden0；小格式补低零精确放入24位。NaN/Inf走special，数值占位0。

第二拍对magnitude做LZD和左移，Aout=decodedExponent−LZC，非零断言顶位1且anchor不溢出。零和special数值占位输出magnitude0、sign0、is_zero1和最小anchor，特殊值flags独立保留。rm/out_type/last同步传递。

in_data/out_data为Valid，延迟2、II1，无反压；valid同步复位，数据仅有效更新不复位。C无乘法器且全PETile仅一份，不能为每个MidGroup重复计面积。

待SV：全部C编码分类、FP32最小subnormal、FP16/BF16精确补零、±0的canonical+0行为、特殊值、last与9拍延迟相位、气泡和复位。
