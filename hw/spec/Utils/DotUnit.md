# K/MN公共batch与C/D实现

对应源码：[DotUnit.scala](../../chisel_src/Utils/DotUnit.scala)。

抽象Module实现K_PE/MN_PE的共同电路，本身不产生额外具体RTL层。完整有序layout在生成时确定，固定物理输入槽位按各PE的wordCount/groupCount前缀切分；每个模式的逻辑K区间由软件映射，inactive槽仍占物理端口，不隐式压缩。能力检查必须两侧均支持且配对合法。

Idle→Accepting→Draining：cfg只在Idle接收，AB/C成对fire；接受last后停止输入，最后D出来回Idle。PE和C在S11会合，原始C先延迟9拍再解码2拍。PE公共F=pe_align_width，补低零到top_align_width公共窗口；C同样精确placement。N个PE+C按topOperandWidth对齐，S14平衡和自然增长ceil(log2(N+1))，anchor同步增长。

S15/16 LZD+sticky，S17/18最终FP32舍入；每个输出只有一份C解码和最终D路径。Valid输出不能反压，batch cfg需保持到last排空。valid/状态复位，payload保持不复位。inactive数值、sign/anchor/special屏蔽，但不把valid=0自动等同于组合路径无活动。

总18级、同batch II1；本轮导出/结构检查不替代K/MN完整握手数值验证，不允许PPA。该模块不是阵列或跨事务累加器。
