# 共用 RTL Testbench

待 spec 确认后实现共用驱动、协议检查与 scoreboard。Chisel 导出和手写 Verilog 导出分别实例化，通过适配层复用相同检查；数据、valid、握手和周期同时验收。当前无可运行 testbench。
