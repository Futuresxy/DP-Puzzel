# LzdNormalize：共享算术/合同

对应源码：[LzdNormalize.scala](../../chisel_src/Utils/LzdNormalize.scala)。

输入Wsum signed和、top_anchor W11、rm/out_type/special/last。第一拍取符号、固定W的二补abs和leading-zero数；最小负数abs仍可作为W位unsigned表示。第二拍左移至最高位，提取outputMantWidth=26：hidden、23fraction、round、sticky。低于提取范围所有位OR进sticky，不能直接裁掉。

原始和坐标为S1/I1/F(Wsum−2)，输出exp=top_anchor−(Wsum−2)+(Wsum−1−LZC)。zero覆盖exp/mant为0，special只传递，真正打包在RoundPack。Full配置Wsum最小43所以总大于W26；源扩展/等宽分支保留但本轮不扫描。

内部含LeadingZeroCounter模块，流水S15/S16，Valid-only延迟2/II1；valid复位0，data有效更新不复位，无反压。待SV检查负数最小值、取消抵消、sticky是否包含全部低位、指数差一位、zero/special和last/气泡/复位。
