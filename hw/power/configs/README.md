# 功耗策略与本机绑定

- [flow-plan.json](flow-plan.json)：选定 Power Compiler，N22 优先 / N12 备选、同源测试数据和方法边界。
- [windows/steady-state-v1.json](windows/steady-state-v1.json)：预热、候选长度、分段及增长稳定性。
- [windows/task-complete-v1.json](windows/task-complete-v1.json)：完整任务边界，长度由事件决定。
- [windows/dp-fixed-macs-v2.json](windows/dp-fixed-macs-v2.json)：当前 K-PE/MN-PE 默认预算 `96×1024 = 98304` 对标量A/B数据，即98304 MAC；H16/Q32/E64对应6144/3072/1536次完整有效调用，其他组织按全DUT每次调用容量整除换算。
- [windows/idle-v1.json](windows/idle-v1.json)：合法 idle 状态、原时钟/输入行为和独立窗口。
- [machines/machine.example.json](machines/machine.example.json)：私有绑定的无路径填写示例；实际文件命名 `machine.local.json`，由 `*.local.*` 忽略。

这些文件均为 `planned` 定义，不能交给现有 DC runner，也不表示已存在 power runner/schema validator。将来实现解析时须维持字段语义或明确升级版本。null 表示尚未绑定，不能当默认可用值；`formal_result_gates` 中的布尔值表示必需条件，不记录任何 run 的通过状态。

technology profile 直接引用 `hw/dc_syn/configs/technologies/`，不再维护第二份 PVT/target_library；库绝对路径和 DB hash 从明确 DC run 取得。power machine 补充仿真标准单元模型、模拟器/SAIF 转换器和 PC 环境入口；许可证仍在获准外部环境中提供，不写入此处。

窗口数值是工程起点，依据和算法见 [窗口策略](../window-policy.md)。改阈值/预算/时间边界、工艺或工具版本形成新 plan/run；不修改历史快照后继续宣称同一实验。

DP 固定数据对/MAC口径与通用稳态增长策略分别使用。98304对标量A/B数据对应98304 MAC、196608 OP，不是98304字节或拍数；初始化、预热和scale/C元数据另计。整除并完成工作量不表示活动已趋稳，若要证明稳态另做检查，不能自动增大预算后仍以原预算命名。

v2的具体数据清单与RTL testbench路径由用户后续在`hw/test`中明确，当前`test_bindings`为pending/null。门级仿真参考该testbench复用激励、握手、结果检查和完成事件，接入冻结DC网表与匹配单元模型采集SAIF；未绑定不执行。原[dp-fixed-macs-v1.json](windows/dp-fixed-macs-v1.json)保留为历史planned配置，不再被默认flow-plan选择。
