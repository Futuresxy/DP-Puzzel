# DP Verilog testbench

[dp_tb.v](dp_tb.v) 是标准 Verilog-2005 testbench，默认驱动纯 Verilog DP，保留显式驱动冻结 SV 版本的历史参考能力。无 class、queue、interface、program、package、动态数组或 DPI；两版 DUT 分别编译。

| Plusarg | 内容 |
| --- | --- |
| `INPUTS` | 共用 `DP_INPUTS_V1` 文件；直接读取 16 字段布局 |
| `GOLDEN` | 每请求一行 FP32/INT32 期望十六进制值，由适配层写出 |
| `SCHEDULE` | 每沿 `reset a_valid b_valid c_valid row_index`；−1 表示无请求 |
| `OUTPUT` | 逐笔 `id result_hex result_type last` 文件 |
| `CUTPOINTS` | 可选 S1–S7 数值断点输出，供 CModel 对照 |

TB 在上升沿 NBA 更新前检查结果和握手；输入在下降沿驱动。输入沿 n 接收，沿 n+8 更新前观察结果。同步复位沿取消 pending 队列，已有数据不跨复位返回。测试结束必须排空流水；`accepted=checked+cancelled`。

复位压力用例中已接收但取消的请求不计入数值通过笔数。非法 datatype 元组应保持三路 ready=0；源填充位、广播、非负 scale 等 payload 约束由用例构造器保证，不要求 DUT 添加 ready 路径检查器。

[run_verilog.py](../run_verilog.py) 管理快照、Verilator lint/build/sim、四态 Icarus 交叉检查、CModel trace；仅显式 `--implementation both` 时做历史双版对比。新功能不要求 SV 同步。所有生成文件位于 `test/runs/verilog/`。TB 的 10ns 时钟只定义仿真事件，不能作为 1.41GHz 时序证据。
