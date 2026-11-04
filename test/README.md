# 新版共用验证环境

状态：目录骨架；等待整体 [spec](../src/spec/README.md) 确认，目前没有可执行的新设计测试。

| 目录 | 职责 |
| --- | --- |
| [cases/](cases/README.md) | 共用用例、逻辑输入及控制事件、固定种子 |
| [reference/](reference/README.md) | 独立数学参考与精度分析 |
| [tb/](tb/README.md) | SV 驱动、协议 monitor、scoreboard |
| [adapters/](adapters/README.md) | CModel 与两条 RTL 路径的薄适配层 |

共用激励、调度、检查规则及报告，按实现选择后端。两套 RTL 对 CModel 的实现一致性要求与相对数学参考的精度指标分别验收；具体合同由 spec 定义。

生成结果放入 `test/runs/`（忽略提交）。设计 RTL 只读取 `hw/rtl/` 的显式导出，不在本目录复制另一份。原 `hw/test/` 保留旧验证资料，其用例、误差阈值及通过状态不自动继承。
