# 格式配对与特殊值

对应源码：[FormatCompat.scala](../../chisel_src/config/FormatCompat.scala)。

沿用源工程W4数据类型及W2 scale码。H只能同类型配对；Q四格式可混合；E2M1/NVFP4可混合；HiF4仅同类型。H的NONE/E8M0输入使用虚拟unit scale；Q和MXFP4要求E8M0，NV要求E4M3，HiF4要求源E6M2。

canonical product在独立解包之后使用：Q统一E5 carrier，E2M1/NV任一侧为NV则采用NV坐标。SpecialValueFlags携带is_nan/is_pos_inf/is_neg_inf，mergeAdd让NaN或异号Inf优先，之后是单符号Inf。纯组合，无时钟/寄存器；非法输入在有效握手/PE valid时断言。需独立验证0×Inf、NaN scale及全部格式边界。
