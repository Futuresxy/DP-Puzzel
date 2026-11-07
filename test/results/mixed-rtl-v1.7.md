# 混合 DP RTL 第二阶段：v1.7.1

CModel 检查点 `49ae9e6` 之后实现 QE lane/group 和三个混合顶层；全部保持 L8/II=1，默认 K_FP16=16、LOCAL_W=28、GLOBAL_W=40。原多精度与 E64 顶层也重新回归，共享解包改动没有借用旧回执。

| 前端 | 固定数据输出 | 数值断点检查 | 导出 ID |
| --- | ---: | ---: | --- |
| t8h16q64e128 | 10747 | 315339 | `DP_verilog_t8h16q64e128_2ffd38fa6ecd68c2` |
| t8h16q32e96 | 10747 | 248145 | `DP_verilog_t8h16q32e96_e6ec3988d4a438c2` |
| t8h16q32e128 | 10747 | 312735 | `DP_verilog_t8h16q32e128_5445bcfaea80f9e9` |
| multi | 10747 | 231654 | `DP_verilog_094a23e8843f8ee1` |
| e | 2883 | 1106924 | `DP_verilog_e_c36605507c4d0709` |

完整 run ID、各精度 exact/max_ulp、各窗口协议计数见 [JSON](mixed-rtl-v1.7.json)。工具为 Verilator 5.030；纯 Verilog-2005 DUT，Verilog TB。严格 lint 无警告，RTL 对有限位宽 CModel 逐位相同；固定数据数学最大误差为原 BF16 的3ULP，新增 Q/E 至多1ULP，没有超过4ULP。此误差结论仅针对已运行语料，不是任意抵消输入的误差保证。

三种混合 profile 分别验证 27/40、28/40、32/64。每组压力测试包含全部 E nibble 组合、e1/e2、scale 编码、C 边界、负零、混精度随机请求、闲置高位毒化、低精度特殊 token 后高精度旁路、非法元组、独立 valid、气泡及同步复位。TB 同时检查 S5 参与资格、每个有效 group/C token、S6 逐叶对齐与共同指数、S7 完整规约值；固定语料全部发出并检查，只有压力测试中的在途请求可被复位取消。

实现：QE 使用八个4×4乘法槽、W8乘积和U6元素指数和；scale指数和仍为9位。共享解包以静态 QE_ONLY 裁掉 T/H/INT8。四个基础组和新增2/4组分别求 MAX，合并共同坐标后逐源移位；S7 基础四组+C 与扩展支分别规约再合并。参与标志跟随请求，关闭支路的 MAX、四种特殊分类及负零各使用正确的归约单位元。C仅加一次，S8仅舍入一次。

复现：构建 CModel 后执行 `python3.11 test/run_mixed_verilog.py --frontend <profile>`；原顶层使用 `test/run_verilog.py --phase all`，E64 加 `--frontend e`。Verilator 路径通过 VERILATOR 环境变量设置，工具链需支持 C++20 coroutine。每个混合回执覆盖11种精度+3个窗口；仅全部通过才开放 DC 门禁。

门禁/综合软件测试35项通过。下一阶段为同库同约束1GHz DC，尚不从本报告推断面积、时序或功耗。

## RTL 规范自检

| # | 检查项 | 结果 | 依据 |
| --- | --- | --- | --- |
| 1 | 常量含义明确 | ✅ | 编码/位宽用 DP 宏；固定 profile 组数与位宽增长公式有说明 |
| 2 | define仅在头文件 | ✅ | 新生产模块未定义宏 |
| 3 | 组合逻辑assign | ✅ | lane/group/MAX/树均为连续赋值与静态结构 |
| 4 | 功能条件按位组合 | ✅ | 参数合法性仿真检查除外 |
| 5 | 无动态多维索引 | ✅ | generate静态槽位与定宽切片 |
| 6 | 显式DFF | ✅ | ff_sN_sM，紧随所属计算级 |
| 7 | 每行单变量 | ✅ | DUT声明拆开；DFF端口按固定紧凑格式 |
| 8 | 寄存器类别 | ✅ | 控制同步低复位，payload保持/使能 |
| 9 | 命名 | ✅ | dp_模块、rN阶段、功能化字段 |
| 10 | 多位数据带en | ✅ | rst_n与本级有效控制 |
| 11 | 目录职责 | ✅ | src开发、test验证、hw导出和EDA |
| 12 | 无多余宏别名 | ✅ | localparam均为派生位宽或结构量 |
| 13 | 信号表达功能 | ✅ | magnitude/exponent/participation等 |
| 14 | 打包边界明确 | ✅ | 复用紧凑M/E/S合同，未添加184位展开接口 |
| 15 | 字段位片明确 | ✅ | DP字段宏、参数化槽偏移，固定profile接口单独声明 |

第二次回归包含 DC elaboration 发现的 DFF 端口位宽修复：multi/QE 的 out_z 和 E group 的 out_anchor/out_z 条件表达式使用显式参数宽度零值，避免无尺寸0把模块端口扩为32位。五个前端均重新完整验证；上表和JSON已指向本次新快照。旧检查点611d58f保留用于回退，不用于后续综合。
