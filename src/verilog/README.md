# 手写 Verilog

状态：等待整体 [spec](../spec/README.md) 和 CModel，当前没有实现。

维护独立手写的可综合 RTL，与 Chisel 对应同一微架构和周期合同；此目录不保存 Chisel 生成代码。输出格式相同不能代替截断位置、流水和协议一致。

通过根目录 [test/](../../test/README.md) 的同一验证环境测试。导出快照集中到 `hw/rtl/<export-id>/`；DC 和功耗分别分析两条 RTL 路径。
