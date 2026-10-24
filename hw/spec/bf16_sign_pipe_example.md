# Bf16SignPipe：DC 流程验收用最小 BF16 示例

这是用户单独授权的手写 SystemVerilog 示例，用于验证 RTL → SV 回归 → 统一证据门禁 → DC 的真实数据链。它不是 BF16 乘加器、计算阵列或 DSE 的面积基线。

BF16 bit 15 为 sign，bits 14:7 为 exponent，bits 6:0 为 fraction。本模块定义位级符号操作：in_negate=0 时逐位透传；=1 时只翻转 sign。不做舍入、缩放、溢出处理或 NaN quieting，所有 65536 种位编码均合法。

| 项目 | 契约 |
| --- | --- |
| 输入 | in_bf16[15:0]、in_negate、in_valid |
| 输出 | out_bf16[15:0]、out_valid |
| 时钟 / 复位 | clock 上升沿；reset 同步、高有效 |
| 周期 | 输入在边沿 k 采样，结果在该边沿后的寄存器输出可见；一层寄存器延迟 |
| 吞吐 | 连续 valid 时每周期 1 个，不支持反压 |
| 精确性 | bit-exact，输出 = 输入 XOR（negate ? 0x8000 : 0） |
| 复位优先级 | reset 时 out_valid=0，忽略当拍输入；数据寄存器保持，不复位 |
| 气泡 | 非 reset 且 in_valid=0 时 out_valid=0，数据寄存器保持 |
| 无效输出 | 不作为数值结果；已初始化后的数据保持仍作为协议属性检查 |

验收覆盖正/负零、正/负有限数、subnormal、最大有限值、Infinity、NaN 位模式和 payload；穷举所有编码 × 两种 negate，共 131072 次有效输入；另加定向、固定种子随机输入、连续 valid、气泡、运行中复位及 reset 与 valid 同拍。

独立 Python 参考生成期望值，SV testbench 对导出 RTL 逐拍比较有效位、数值和保持属性；只有真实仿真进程成功且计数匹配才生成 passed 回执。功能仿真的 10 ns 时钟仅用于周期检查，不是 DC 的时序测量；综合单独采用显式指定的约束。

源模板在 dc_syn/examples，实际设计 .sv 只由公共脚本写入 hw/rtl 的独立 export。模板按原字节导出，没有 Chisel 编译步骤；来源类型明确记为 systemverilog，chisel_class=null。
