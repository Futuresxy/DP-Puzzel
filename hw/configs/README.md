# Full 复用硬件配置

唯一实现为 SubPE → PEGroupFull → MidGroupFull → PETile；集中参数见 [Parameters.scala](../chisel_src/config/Parameters.scala) 与 [spec](../spec/config/Parameters.md)。没有第二套扁平实现或旧 mn/k 配置。

| 配置 | 结构 |
| --- | --- |
| [full_h16q32e64.json](full_h16q32e64.json) | 1 MidGroup / 4 PEGroup / 16 SubPE，共享一次 C/D |
| [full_h48q96e192.json](full_h48q96e192.json) | 3 MidGroup / 12 PEGroup / 48 SubPE，覆盖非二次幂 K 规约 |

```json
{"schema_version": 1, "mid_groups": 1, "align_width": 40}
```

mid_groups 允许1–4，align_width允许40–64，所有值必须为整数；schema严格拒绝额外字段、旧kind/pes和非法范围。每个MidGroup固定H16/Q32/E64，容量按实例数推导，三者是互斥模式的每次接收容量，不能相加。

选择另一个配置即可改变完整MidGroup数和跨组/C对齐窗口，无需修改Chisel。固定局部位宽、scale编码与18级流水不作为独立旋钮。运行格式在batch cfg中锁定，不写进结构JSON。

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate config configs/full_h48q96e192.json
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/full_h16q32e64.json "full reuse review"
```

Mill0.11.8、Scala2.13.12、Chisel6.4.0、firtool1.62.0固定。导出带配置/源码hash和独立时间ID；生成成功仍为generated，必须对同份RTL完成SV数值/周期回归后才允许进入PPA。配置不包含全芯片核心数/HBM/阵列布局。
