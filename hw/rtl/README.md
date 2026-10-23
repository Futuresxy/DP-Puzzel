# 全项目唯一 RTL 来源

后续每次导出使用以下目录名：

    <Top>__<config-id>__<YYYYMMDDTHHMMSSffffffZ>__<source-sha12>/

| 文件 | 责任 |
| --- | --- |
| README.md | 每次导出及验证状态更新的可读记录 |
| manifest.json | 源码/Git/参数/工具指纹、模块映射、文件 hash、验证证据 |
| files.f | 相对导出目录的设计文件清单 |
| src/<Module>.sv | 一个 module 一个独立同名文件 |
| export.log / test.log | 最小必要日志；大型产物在各 run 目录 |

这是未来产物契约，目前未生成上述文件。测试、DC、功耗均显式引用 export ID 与同一份清单，不复制设计 RTL，不在导出后手工修补。参数特化和工具辅助模块须列明与 Chisel 源的对应关系。

状态流：generated → RTL-verified → 可被综合/功耗引用。失败标记 failed；源码、参数或工具变化形成新导出；RTL hash 不符阻止分析，验证代码变化需要重测。分析 run 自身具有独立状态。

README 每次记录时间、目的、参数、版本、命令、文件映射和状态。失效且无引用的 RTL 可删除，但保留原因与最小复现信息。被论文/characterization 引用的 RTL 应保留一份可核验的归档，不能因清理破坏复现链。

完整导出目录默认忽略；核心可复现信息和小型摘要经整理后提交。未启用任何“最新 RTL”隐式入口。
