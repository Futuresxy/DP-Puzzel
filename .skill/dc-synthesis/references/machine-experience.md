# 本机流程来源与复用边界

通用 DC 入口移植自本仓库 `be850fc04659c42ce65badde75557bae1776aa69`。
其 N12 profile 参考既有项目设置：TSMC CLN12FFCLL / BWP6T16P96CPD 120a，
base+LVT、TT 0.7 V / 85°C，LVT 数量上限 20%。该设置为分析角，不是所有工况签核。

本任务重新核验实际 DB/Liberty/LEF 和 X-2025.06 工具，未移用旧项目面积或时序。
本机主 PDK 挂载可能返回 Key has expired，备用挂载若同版本同 corner 可读则可绑定。
机器路径、环境和原始库报告留在忽略目录，不提交 PDK 或许可证信息。

沙箱许可证连接失败曾返回 DCSH-1；在获准的本机环境核验成功后才执行。
`report_lib` 另依赖 Library Compiler，本机未配置该命令；环境探测使用
DC 的 read_db/get_libs/get_lib_cells，加上 Liberty 元数据和同版 LEF 单位核对。
不得将环境探测通过当成 RTL 综合通过。

真实结果、失败原因和时序分析见 `hw/dc_syn/records/`；功耗另需一致性与活动证据。
