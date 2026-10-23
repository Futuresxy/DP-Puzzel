# Arithmetic.scala：内联算术基础单元

对应源码：[Arithmetic.scala](../../chisel_src/common/Arithmetic.scala)。这些函数在调用模块中生成电路，不引入计算层级；只有 `delay` 生成显式流水寄存器。

| 函数 | 电路与理由 | 数值要求 |
| --- | --- | --- |
| signed | 无符号 magnitude 增加符号位后条件取负 | 可表示全幅 magnitude，避免先有符号化导致溢出 |
| append | 显式低位补零 | 不丢精度，但改变固定点小数位置 |
| shiftSticky | 分级 barrel shifter，并 OR 每级丢弃位 | 超过宽度时输出 0、sticky 为原输入非零 |
| shiftRtzParts | 算术右移 floor 与负数尾部修正 bit 分开 | `RTZ(x,s)=floor(x/2^s)+(x<0且丢弃位非零)` |
| delta | 13-bit 指数差后饱和到数据宽度 | 输入 maximum 不小于参与对齐的有效 anchor |
| maximum | 平衡比较树，同时携带最小获胜索引 | 同值时优先低索引，支持非二次幂输入数 |
| align | MAX 与 slot0 交换、N−1 路右移、修正计数 | MAX 不移位，交换不改变加法规约结果 |
| sum | 每层 3:2 CSA 压缩至两行，再一次 CPA | 调用方提供足够总和位宽；中间模 2^W，最终不得溢出 |
| leadingZeros | 二叉树 LZD，不满二次幂在低端补零 | 零返回原宽度，非零不因补零改变 LZC |
| delay | 固定长度 RegEnable 与 valid 流水 | valid 复位，数据仅在对应有效拍更新 |

`align` 的返回值是 floor 列表及 correction 总数，必须一起送入 `sum`；忽略 correction 会把负数截断变成向负无穷舍入。其 MAX 旁路省一个 barrel，交换网络仅在 slot0 与 winner 之间，不需要构造完整动态排列。

CSA 的每一层同时压缩互不重叠的三行，避免把输出立刻投入下一组三输入造成串行压缩链。保留进位位数通常为 `ceil(log2(N))`；加 RTZ correction 不增加理论最终上界，但输入范围证明仍属于调用者。

这些优化仅表达结构，尚无综合面积或时序证据。逻辑没有异步状态、锁存器或生成时钟。

待验收：负数最小值、移位 0/W/大于 W、符号修正、所有零、重复 MAX、N=1/2/3/4/5、奇数位宽 LZD。辅助 Chisel 检查可做，但最终以调用模块的 SV RTL 数值/周期验证为依据。
