# 后续模板职责

当前仅定义职责，没有 Tcl / testbench 模板实现。

- 门级回放模板：连接已验证接口、共用测试 driver/scoreboard、合法初始化、同源时钟与窗口事件，直接 SAIF 或 gate VCD 采集；设计 RTL 与网表均通过显式路径原位引用。
- Power Compiler 模板：读取冻结 mapped Verilog、匹配 DB 和 SDC，核对 top/units/库/周期，清理旧活动、读取指定 SAIF，保存 `report_saif`、功耗和关键计算报告；不执行 compile/ECO。
- 结果报告模板：关联源 DC 的面积/setup/hold、工况、task/steady/idle 功耗、活动审计、收敛、未执行项与归档索引。

模板由未来公共 prepare 按输入快照到 run，并记录 hash；run 快照不能反向成为维护入口。工具版本命令及标准单元模型兼容性必须经真实验收，不能依据文档完整或 Tcl 语法完整就宣称分析已通过。
