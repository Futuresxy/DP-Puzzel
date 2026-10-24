# 本地功耗 run

未来每个 run 在独立 `runs/<power-run-id>/` 中创建；除本文件外均被 Git 忽略。当前没有 run 或功耗测量。

文件树与引用边界见 [paths.md](../paths.md)。同一个明确 DC run 可被多个格式/数据集功耗 run 只读引用；不在此复制设计 RTL、综合网表或 canonical 测试数据，不覆盖历史目录或创建 latest。

完整日志/波形含私有信息时留本地或受控归档，长期精简记录经审查转入 [records](../records/README.md)。删除产物前确认下游引用及恢复方式，不能仅保留 hash 就声称原波形/网表可恢复。
