# 参数与结构展开入口

对应源码：[Elaborate.scala](../../chisel_src/elaborate/Elaborate.scala)。

module构造PE/MN/K，统一传入AlignmentConfig。review覆盖六种PE及各自MN、4种K布局、三组窗口/guard边界以及K高宽度，总35种结构。只有HQE/QE/E计入实际PG/SubPE数量；H/Q要求没有这些实例，所有路径都不再生成PEAlignNormalize/PEGlobalAlignNormalize模块。11类非法参数/shape在构造阶段拒绝。config <JSON>支持四个--width覆盖，真实调用解析器与Generate相同。

仅emitCHIRRTL，warnings-as-errors，不执行DUT。结构成功不代表精度、周期协议或PPA通过；定向RTL检查另由显式export脚本运行。输出摘要不保存临时RTL。
