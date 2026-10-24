# packed输入与batch接口

对应源码：[Interfaces.scala](../../chisel_src/Utils/Interfaces.scala)。

VectorInputBundle以W16 word为存储单位，另带dtype、W8主scale和HiF4 g0/g1。每PG四word、一个scale槽、4g0/2g1；PE_g4是16word/4scale/16g0/8g1，PE_E_g2为8word/2scale/8g0/4g1。

PETileConfig在K/MN入口为batch握手，包含独立A/B dtype/scale、C格式和舍入；接受后保持到last排空。PE直接输入cfg为稳定电平，不能有在途事务时切换。AB payload的重复格式字段在K/MN入口检查一致；基础PE以cfg为权威并覆盖组输入的重复字段；内部Valid不提供反压。

C carrier W32，FP16/BF16放低16bit；最终输出FP32 result/last。Bundle无额外流水或复位；尾块由上游补0。scale物理槽位随profile记录，不能把不同块隐式合并。
