# 自然宽度的无损规范化

对应源码：[PENormalizeExact.scala](../../chisel_src/Utils/PENormalizeExact.scala)。

输入signed W位和、物理raw_top_anchor和special；value=R*2^(Araw−(W−2))。两级先扩W+1取abs并LZD，再把最高1移到bitW−2，Aout=Araw+1−LZC。最小负数abs=2^(W−1)时精确右移1并anchor+1；zero固定sign0/magnitude0/anchor=-1024。

输出W−1 magnitude与独立sign，内部过程无损、不舍入。Valid-only延迟2、II1；valid复位，data有效更新。HQE/QE/E直接或精确补零到公共输出；H/Q在本模块之后显式RTZ到公共窗口，不能把H/Q最终转换也称为无损。非零anchor溢出与顶位位置有断言。
