# 历史 Chisel 设计归档

2026-11-04 按用户要求，将原 `hw/chisel_src/`、`hw/build.sc` 和 `hw/.mill-version` 移入此目录。保留当前工作区内容，包括归档前已有的修改；Scala 内容不因整理目录而改写。

- [chisel_src/](chisel_src/README.md)：旧五族六种 PE 和 K/MN 实现，仅供参考。
- `build.sc`、`.mill-version`：历史构建定义，仅保存原环境信息，不是新版构建入口。
- [../spec/](../spec/README.md)、[../configs/](../configs/README.md)、[../test/](../test/README.md)：旧规格、配置和验证资料仍在原位置。
- [../rtl/](../rtl/README.md)：已有导出保留原 ID 与来源记录，不因源码归档改写历史 manifest。

旧命令以当时 `hw/` 工作目录和文件布局为前提。归档不承诺直接从本目录执行构建或导出；如需复现实验，先恢复独立历史工作区及对应工具/输入，不能向新设计目录写入旧构建产物。旧源码内的路径字符串和历史 manifest 属于原版本语境。

新设计入口是根目录 [src/](../../src/README.md)，统一测试在 [test/](../../test/README.md)。旧结构、格式支持、位宽、流水和验证结论不构成新版合同。
