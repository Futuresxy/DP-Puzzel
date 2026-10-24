# 工艺与本机配置

`technologies/` 是可提交的库标识/PVT profile，当前有 N22 TT 0.9 V/85°C 与 N12 base+LVT TT 0.7 V/85°C；不携带库内容或私有路径。文件是参考项目经验配置，不代表本项目已完成真实环境验收。

`machines/machine.example.json` 是无私有信息的填写模板，复制为同目录 `machine.local.json` 后绑定真实 DB、工具和环境入口；local 文件由全仓库 `*.local.*` 规则忽略。许可证在获准环境中提供，不写 JSON。

时序/综合策略在 `../constraints/`，避免与 PVT 或机器位置混合。字段见 [输入契约](../input-contract.md)，全部目录及产物位置见 [路径定义](../paths.md)。
