# MN_PE：基础PE编排入口

对应源码：[MN_PE.scala](../../chisel_src/core/MN_PE.scala)。

恰好一个基础PE加独立C/D，构成一个未来M/N输出位置；不包含阵列或多输出复制。

构造参数为PE布局/单PE与AlignmentConfig，完整传递到DotUnit及各基础PE。配置默认来自Parameters；JSON/CLI同样生效。总18级、II1、batch固定格式、原子AB/C接受，输出无ready；控制复位/数据保持。公共实现和数值限制见 [DotUnit](../Utils/DotUnit.md)。未执行完整RTL数值协议回归或PPA。
