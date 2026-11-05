# 综合与功耗分析

[设计源码与规格](../src/README.md) 在 `src/`，[功能、数值和周期验证](../test/README.md) 在 `test/`。

| 目录 | 内容 |
| --- | --- |
| [rtl/](rtl/README.md) | 每个分析对象的只读 RTL 快照、顶层、端口与验证来源 |
| [dc_syn/](dc_syn/README.md) | DC 配置、面积/时序、工具流程测试和本机 run |
| [power/](power/README.md) | 真实负载活动与功耗分析 |
| [characterization/](characterization/README.md) | 面向 `ratio_dse` 的可追溯特征数据 |

RTL 从 `src/` 冻结到 `hw/rtl/<export-id>/`，由 `test/` 回归。DC 和功耗按显式 export ID 与真实通过回执选定输入。DC 的网表、完整报告和日志放在本机 `dc_syn/runs/`，可共享的精简结果进入 `records/`。
