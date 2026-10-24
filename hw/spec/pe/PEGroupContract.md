# PEGroupContract.scala：组级固定周期

对应源码：[PEGroupContract.scala](../../chisel_src/pe/PEGroupContract.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

固定 anchorWidth=11、anchorToDataLatency=1。PG 在 S06 发布 zero-masked anchor，S07 发布 scaled data；MidGroup 在 S07 注册 MAX、S08 对齐同一事务数据。不能用两个独立 ready 让它们错拍。

只提供 Scala 固定常量，不创建 Module、状态或复位。改 anchor 发布周期必须同步 PG/MidGroup valid 寄存和规约，不允许只改常量。待 SV scoreboard 同时检查气泡/复位后的两路相位；本轮展开只检查连线和类型。
