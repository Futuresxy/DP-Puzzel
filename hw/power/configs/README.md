# 功耗策略与本机绑定

- [flow-plan.json](flow-plan.json)：选定 Power Compiler，N22 优先 / N12 备选、同源测试数据和方法边界。
- [windows/steady-state-v1.json](windows/steady-state-v1.json)：预热、候选长度、分段及增长稳定性。
- [windows/task-complete-v1.json](windows/task-complete-v1.json)：完整任务边界，长度由事件决定。
- [windows/idle-v1.json](windows/idle-v1.json)：合法 idle 状态、原时钟/输入行为和独立窗口。
- [machines/machine.example.json](machines/machine.example.json)：私有绑定的无路径填写示例；实际文件命名 `machine.local.json`，由 `*.local.*` 忽略。

这些文件均为 `planned` 定义，不能交给现有 DC runner，也不表示已存在 power runner/schema validator。将来实现解析时须维持字段语义或明确升级版本。null 表示尚未绑定，不能当默认可用值；`formal_result_gates` 中的布尔值表示必需条件，不记录任何 run 的通过状态。

technology profile 直接引用 `hw/dc_syn/configs/technologies/`，不再维护第二份 PVT/target_library；库绝对路径和 DB hash 从明确 DC run 取得。power machine 补充仿真标准单元模型、模拟器/SAIF 转换器和 PC 环境入口；许可证仍在获准外部环境中提供，不写入此处。

窗口数值是工程起点，依据和算法见 [窗口策略](../window-policy.md)。改阈值/预算/时间边界、工艺或工具版本形成新 plan/run；不修改历史快照后继续宣称同一实验。
