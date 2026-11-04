# 单 DP 手写 RTL 验证 · v1.4

记录时间：2026-11-04 23:42:09 +08:00。Verilog 为主要交付，SystemVerilog 为对照；同一份纯 Verilog testbench，全部仿真读取冻结源码快照。

## 1. 结果

| 检查 | 每版结果 |
| --- | --- |
| 原九格式，共用 correct_961 | 8649 / 8649 逐位匹配 |
| TF32 K8 / INT8 K32 | 1053 / 1045，全数匹配 |
| 默认配置合计 | **10747 / 10747** |
| 六组参数与混格式流 | 接收 3168；输出 **2922 / 2922**；复位取消 246 |
| 非法 datatype 元组 | 30 次尝试全部拒收，不进入流水 |
| S1–S7 CModel 数值断点 | **231654 / 231654** |
| Verilog ↔ SystemVerilog | 17 组输入/输出文件 SHA 完全一致 |
| Verilator ↔ Icarus（Verilog） | 17 组输出文件 SHA 完全一致 |
| RTL lint | 两版六组配置全部通过；位宽、锁存器、组合环未豁免 |

通过含义为 RTL 与已验证的有限窗口 CModel 位精确一致。数学参考与有限 RTZ 误差见 [CModel 报告](cmodel-v1.4.md)；不能将本报告解释为所有格式均等于无限精度点积一次舍入。复位取消的 246 笔不计作数值通过。

## 2. 参数覆盖

| K_FP16 | LOCAL_W / GLOBAL_W | accepted / checked / cancelled | 断点 |
| --- | --- | --- | --- |
| 4 | 27 / 40 | 528 / 487 / 41 | 17405 |
| 8 | 27 / 40 | 528 / 487 / 41 | 33308 |
| 16 | 27 / 40 | 528 / 487 / 41 | 65114 |
| 4 | 28 / 48 | 528 / 487 / 41 | 17405 |
| 8 | 32 / 64 | 528 / 487 / 41 | 33308 |
| 16 | 32 / 64 | 528 / 487 / 41 | 65114 |

每组参数含 48×11 个混格式随机请求（种子 20271105）、5 个非法格式元组、独立 valid 到达、气泡、last、在途复位。最后的 5 个非法请求不被接受。K4/K8/K16 覆盖最终加法树 2/3/5 项。

S1 比较每个 atom 的 M16/E10/S4；S2 比较所有活动产品与组 r；S3 比较局部 TC 叶；S4 比较 lane SOP；S5 比较组/C 幅值、符号、anchor、z、特殊摘要；S6 比较全局叶与 E_max；S7 比较完整自然位宽的总和。INT32 溢出通过完整 S7 和及低 32 位输出核验，异常不是 DUT 外部端口。

## 3. 快照与复现

| 实现 | RTL_ID |
| --- | --- |
| verilog | `DP_verilog_ae27f3c82d6e3ff5` |
| systemverilog | `DP_systemverilog_1cb52fa504452c67` |

工具：Verilator 5.020、Icarus Verilog 12.0、g++ 13.3.0。Verilator 在本次环境以用户目录中的 Ubuntu 软件包运行；仓库不提交工具二进制或机器路径。

```sh
# 先构建 src/cmodel
python3 test/run_verilog.py --phase all
python3 test/run_verilog.py --simulator iverilog --implementation verilog --phase all
```

Verilator 可通过 `--verilator` 或 `VERILATOR` 环境变量选择。源/快照 SHA、工具、参数、输入/输出指纹及逐组统计保存在 [机器摘要](verilog-v1.4.json)。快照可由同一源码重新生成；原始运行日志、逐笔输出、断点与模拟器构建目录在 `test/runs/verilog/`，不进入 Git。

非功能 RTL lint 豁免为 UNUSEDPARAM、UNUSEDSIGNAL、VARHIDDEN，分别对应公共常量、显式冗余位/观察点、各 Verilog 模块中的共用函数展开；TB 编译另允许文件读取 integer 宽度、timescale 和初始化调度告警。RTL 先单独严格 lint，TB 豁免不会隐藏 RTL 位宽问题。

## 4. 边界

仅验证单 DP 的 L8 主方案。没有 Chisel、计算阵列、L9、门级仿真或 DC/STA/功耗；1.41GHz 仍待工艺库下的后端证据。其他窗口组合尚未逐一验证。两种语言的功能一致不能作为面积/功耗优劣的结论。
