# 全项目唯一 RTL 来源

后续每次导出使用以下目录名：

    <Top>__<config-id>__<YYYYMMDDTHHMMSSffffffZ>__<rtl-sha12>/

| 文件 | 责任 |
| --- | --- |
| README.md | 每次导出及验证状态更新的可读记录 |
| manifest.json | 模块/文件路径映射、单个 RTL 目录指纹和真实验证证据路径 |
| files.f | 相对导出目录的设计文件清单 |
| src/<Module>.sv | 一个 module 一个独立同名文件 |
| export.log / test.log | 最小必要日志；大型产物在各 run 目录 |

该契约已由用户授权的 Bf16SignPipe 手写示例形成实际 export；完整 Chisel exporter 仍待实施。测试、DC、功耗引用 export ID 和同一清单，不复制或手改导出 RTL。Chisel 模块记录类/参数来源；手写示例记录 systemverilog 类型及源模板路径，并检查逐字节一致性，不虚构 Chisel 类。

已实现只读的 [统一证据门禁](../../scripts/rtl_gate.py)，字段见 [v2 契约](../dc_syn/input-contract.md)。指纹只覆盖 files.f + src/ 全部路径与内容，不为单个文件另存摘要；验证和综合绑定同一目录指纹。门禁不生成 PASS，DC 仅接受真实回归通过的 export。

状态流：generated → RTL-verified → 可被综合/功耗引用。失败标记 failed；源码、参数或工具变化形成新导出；RTL hash 不符阻止分析，验证代码变化需要重测。分析 run 自身具有独立状态。

README 每次记录时间、目的、参数、版本、命令、文件映射和状态。失效且无引用的 RTL 可删除，但保留原因与最小复现信息。被论文/characterization 引用的 RTL 应保留一份可核验的归档，不能因清理破坏复现链。

完整导出目录默认忽略；核心可复现信息和小型摘要经整理后提交。未启用任何“最新 RTL”隐式入口。
