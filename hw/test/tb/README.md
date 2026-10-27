# 六个固定 RTL testbench

每个 TB 直接实例化自己的 DUT，固定端口接线保存在源码中，不在运行时生成 adapter：

| TB | DUT默认名 | 物理字数 | H/Q/E native K |
| --- | --- | ---: | --- |
| tb_k_1_2_4.sv | K_PE_H16Q32E64 | 16 | 16/32/64 |
| tb_k_1_2_6.sv | K_PE_H16Q32E96 | 24 | 16/32/96 |
| tb_k_1_2_8.sv | K_PE_H16Q32E128 | 32 | 16/32/128 |
| tb_k_1_4_8.sv | K_PE_H16Q64E128 | 32 | 16/64/128 |
| tb_mn_e_g4.sv | MN_PE_H0Q0E64 | 16 | 0/0/64 |
| tb_mn_qe_g4.sv | MN_PE_H0Q32E64 | 16 | 0/32/64 |

`DUT_MODULE` 编译宏可选择同形状、不同窗口后缀的实际模块名。固定 TB 定义 WORD_COUNT、MID_COUNT、mid_words()/mid_kind()，公共 `pe_tb_signals.svh` 定义信号，`pe_tb_common.svh` 实现读取、packing、驱动和 monitor。TB 不读取 golden，也不内置数值期望。

输入接口为 `+INPUT_FILE=... +OUTPUT_DIR=... +RTL_ID=... +SCHEDULE=0/1`。从文件头读取事务数、逻辑K、格式和scale/group数量。每次只读取一个事务的逻辑元素，按固定 MidGroup layout 打包和放置；输入 valid 拉高后保持数据直到 AB/C 原子握手，随后读取下一笔。

monitor 在上升沿 NBA 前观察传输，driver 在下降沿改输入；接受于N沿的事务在N+18沿观察结果。64项环形 scoreboard 保存在途事务的接受周期；数据量增长不增加全批数组或编译参数。超时随事务数增长，已用2048/10000笔重放验证。

continuous 检查全批 II=1；bubbles 前32笔连续，之后按事务号模7/11/13插入共同气泡以及AB先到/C先到的延迟。接受 input last 后继续提供额外事务，检查Draining禁止接受；最终last排出后检查Idle，并额外观察8拍防止迟到/重复输出。每个 case 单独初始复位，尚不包含运行中复位、多batch连切及全部舍入模式。

输出：

- `rtl_result.txt`：每行一个实际 DUT FP32 HEX，无表头，方便 Python 直接读取。
- `transactions.txt`：TAB表头 txn/result_hex/accept_cycle/result_cycle/latency/last。
- `protocol.txt`：RTL_ID、输入文件、接受/完成数量、延迟、调度。
- `comparison.txt`：独立 Python 合并 actual/golden 后的逐项 ULP、Exact、状态和可读数值。
- `segments.txt`：correct_961中五段的边界、Exact、最大ULP和通过状态。
- `report.json`、`simulation.log`：逐case摘要和仿真器/DUT assert输出。

raw 输出由其所在的显式 export/run/case 目录，以及 protocol.txt 中的 RTL_ID 对应设计；顶层 RTL 文件头使用同一标识。新流程不生成逐文件 SHA，依赖只读导出与唯一目录；旧版 TB/adapter 源码保留在 legacy/v1。

默认正确性测试读取correct_961，连续发送961笔，只在文件最后一笔拉高input last。原64/128/256/512/1分段边界由Python报告识别，不拆成独立batch。默认continuous；气泡调度可用--schedule选择。
