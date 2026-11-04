# SystemVerilog 对照实现

保留的手写 SystemVerilog 版，与主目录纯 Verilog 版遵守同一 DP v1.4 算术与 L8 合同。只包含单 DP；没有计算阵列或 Chisel 生成代码。

编译入口为 [files.f](files.f)，先编译 `parameter/dp_pkg.sv`。module 名与 Verilog 版一致，必须使用独立编译目录。验证复用 [纯 Verilog testbench](../../../test/rtl/dp_tb.v)；命令、参数与覆盖范围见 [上层说明](../README.md)。

此目录是语言表示的对照，不是独立移位对齐架构。功能一致不能据此认定两种语言的综合面积或功耗存在差异。
