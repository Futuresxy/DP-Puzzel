# Elaborate.scala：源码审查展开入口

对应源码：[Elaborate.scala](../../chisel_src/elaborate/Elaborate.scala)。Host-side Scala main，不是可综合硬件，不导出 RTL 文件。

固定使用 Chisel 6.4.0 `ChiselStage.emitCHIRRTL`，生成内存中的 CHIRRTL 以检查参数合法性、Bundle 连接、已知位宽及层级。开启首错退出和 warnings-as-errors，防止把动态索引宽度等结构警告留到 EDA 阶段。`module(config)` 是检查和导出共用的顶层构造函数，使 config 包只保存数据/合法性而不依赖 core 电路类。

在 `hw/` 下调用：

```sh
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate config configs/mn_h16q32e64.json
mill -i pe.runMain dp.elaborate.Elaborate pe H0Q32E0
mill -i pe.runMain dp.elaborate.Elaborate mn H0Q0E32
mill -i pe.runMain dp.elaborate.Elaborate k H16Q32E64 H0Q0E32
```

review 覆盖八种合法基本 PE 组合及相应 MNPE、KPE 的 1–4 个 Full、两个异构布局、W64 结构边界；列出展开模块并禁止旧 SubPE/PEGroup/MidGroup 层级。CHIRRTL 中同构 PE 可能带工具生成的数字后缀，后续 firtool 可以去重，实际 RTL 映射以导出 manifest 为准。

结构展开不是逻辑仿真，不验证数值正确、协议运行、综合时序或功耗，也不生成 passed 状态。它不能替代未来 SystemVerilog testbench 的 RTL 验收。

参数化 RTL 导出由独立 [Generate](Generate.md) 入口负责，避免把检查模式的临时文件误作正式导出。工具缓存位于忽略的 hw/out，不在源码或 spec 中保存编译器中间产物。
