# Elaborate.scala：四层 full 结构检查

对应源码：[Elaborate.scala](../../chisel_src/elaborate/Elaborate.scala)。Host-side main，不是硬件Module；检查与Generate共用 `module(DesignConfig)`，只构造当前唯一的PETile。

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate config configs/full_h16q32e64.json
```

Chisel6.4.0在内存生成CHIRRTL，开启throw-on-first-error/warnings-as-errors，不写RTL文件。review与full-review为同义入口，覆盖mid_groups1/2/3/4、默认W40和N1/W64；检查每份实际展开的PETile/MidGroup/PEGroup/SubPE数量为1/N/4N/16N。N3覆盖非二次幂规约。

构造/JSON拒绝检查覆盖mid_groups0/5、window39/65、非整数数量、未知字段和旧kind/pes schema。旧pe/mn/k命令已经移除，不能默默生成其他实现。

CHIRRTL的同构实例在去重前可能各有带数字后缀的module定义；真正split RTL的定义去重与物理实例数量不同，需结合 [导出检查](Generate.md) 核对。结构展开没有执行DUT，不证明数值、运行协议、时序或功耗，不会生成passed状态，也不替代后续SV回归。
