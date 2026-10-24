# 时序约束职责

后续按已确认接口维护时钟、IO 延迟、输入转换、输出负载、复位和必要时序例外。所有值来自设计/PVT要求，不用示例 1 ns 代替真实目标；变更随综合 run 记录 hash。

当前不保存生成 SDC；显式 JSON 约束由 `../templates/DC.tcl` 应用，并在每份 run 的 `netlist/<Top>.sdc` 导出。参考预算在 `../constraints/reference-1410mhz.json`，无默认启用的目标工况。v1 为单时钟/统一 IO，min/max 独立，不包含时序例外；新增例外先更新契约和验收，不能编辑 run 快照。
