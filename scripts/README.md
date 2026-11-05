# 公共流程入口

- `rtl_gate.py EXPORT_ID` 校验 `hw/rtl/` 中的指定快照和 `test/runs/` 中的真实通过回执。
- `dc_syn.sh` 执行 DC 输入检查、准备、综合与报告。用法见 [DC 说明](../hw/dc_syn/README.md)。
- `research/` 保存外部参考平台的编译与分析工具。

设计维护在 `src/`，功能回归在 `test/`，综合和功耗分析在 `hw/`。入口使用明确的配置与 ID。
