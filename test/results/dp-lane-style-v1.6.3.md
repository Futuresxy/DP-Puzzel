# dp_lane 阅读性修订验证 · v1.6.3

基线：feat/dp-verilog-v14 / c352bd8；只迁移多精度 dp_lane 内部命名及排版，未迁移其他 DUT 或冻结 SV。默认 K16/28/40，L8/II=1 保持。

- r1_valid～r4_valid 代替 valid_q[0..3]；rN_ 前缀表达寄存级，功能名_d 表达组合候选。
- a_decoded_data/b_decoded_data 说明解包数据视图；乘积、指数、特殊分类、对齐叶子均明确功能。
- 参数/端口/局部变量声明前说明用途，接口分区、等号对齐、完整函数/分支换行；DFF 就地紧凑排列。
- TB 使用当前/冻结 SV 分离的内部探针别名；CModel、数据和算术未修改。还原名称及 valid 分量后核对操作数、运算符和连接一致，只增加条件分组括号。

## 最终回归证据

| 项目 | 结果 |
| --- | --- |
| Run ID | `20261106T070422038543Z` |
| Export ID | `DP_verilog_bbffe20dbfa3a151` |
| 源指纹 | `bbffe20dbfa3a1517c7cb97babb701c8d665a10141613dda128edf6112003b1f` |
| 回执 SHA-256 | `643ebd74d548d594cc829bf8c4c1d252eb717771f083ed80478a15cc19f73ea6` |
| 固定向量 | 10747 笔全部与有限位宽 CModel 一致 |
| 参数 | K4/27/40、K8/27/40、K16/28/40、K4/28/48、K8/32/64、K16/32/64 全部通过 |
| 混合协议 | 每组 accepted=528、checked=487、reset_cancelled=41；复位取消在途请求 |
| 断点 | 231654 个通过；S1–S7 数值与模型一致 |
| lint | 六组参数 Verilator 5.030 严格 lint 通过 |
| 排版 | Verible 重放保留局部保护区，完整函数/三目分支不被拆开 |

固定集数学参考误差：BF16 max_ulp=3，FP16/TF32/MXFP8 E5M2=1，其余浮点固定集为0；INT8 为逐位检查。golden_exact 和数学误差属于不同判据。

命令：`python3.11 test/run_verilog.py --implementation verilog --phase all`。本机使用 Verilator 5.030、GCC toolset 10、CCACHE_DISABLE=1、CXXFLAGS=-std=c++20 -fcoroutines。首轮通过后微调三目列对齐，以上最终源码重新完成整轮验证。未执行 E 数值回归、DC 或功耗；旧证据对应各自快照，不由本次风格检查授予新 PPA 结论。

本批按普通运行保留；精简摘要/当前回执引用的证据受保留规则保护。结束后释放两轮临时 Verilator C++/对象/二进制，保留输入、逐笔结果、断点、日志和回执；不标记重要节点。

## 本次自检

| 项目 | 结果 |
| --- | --- |
| 常数语义、宏仅在 .vh、assign 组合逻辑 | 均通过，未改数值常量/运算 |
| 条件按位组合、显式选择、DFF 保存 | 均通过，寄存连接/使能不变 |
| 单变量声明、寄存类型、功能命名 | 均通过，明确 rN 阶段与解包视图 |
| payload 使能、目录职责、localparam 无纯别名 | 均通过，未扩大 DUT 迁移范围 |
| 信号功能、打包解包、字段切片 | 均通过，新增声明注释并同步探针 |
