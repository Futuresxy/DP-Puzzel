# 后续模板职责

当前仅定义职责，没有 Tcl / testbench 模板实现。

- 门级回放模板：以用户后续指定的`hw/test` RTL testbench为依据，复用激励/driver、时钟与握手、事务顺序、golden/scoreboard、合法初始化及完成事件；DUT接为冻结DC网表与匹配单元模型，增加窗口控制和直接SAIF或gate VCD采集。当前数据/testbench路径待绑定，不预填文件，不修改设计RTL或原始测试数据。
- Power Compiler 模板：读取冻结 mapped Verilog、匹配 DB 和 SDC，核对 top/units/库/周期，清理旧活动、读取指定 SAIF，保存 `report_saif`、功耗和关键计算报告；不执行 compile/ECO。
- 结果报告模板：关联源 DC 的面积/setup/hold、工况、task/steady/idle 功耗、活动审计、收敛、未执行项与归档索引。

模板由未来公共 prepare 按输入快照到 run，并记录 hash；run 快照不能反向成为维护入口。工具版本命令及标准单元模型兼容性必须经真实验收，不能依据文档完整或 Tcl 语法完整就宣称分析已通过。
