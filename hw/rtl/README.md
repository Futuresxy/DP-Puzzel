# EDA 的 RTL 输入目录

每次分析使用独立的 `hw/rtl/<export-id>/`。从 `src/` 导出或冻结待测 RTL，使用根 `test/` 的 testbench 验证，再将同一目录交给 DC 或功耗流程。分析入口显式选择 export ID。

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 顶层模块、时钟/复位接口、来源、目录指纹、验证状态和回执路径 |
| `files.f` | 相对该目录的有序文件清单和所需 include 路径 |
| `src/` | 清单里的设计 RTL 和头文件 |
| `README.md` | 导出命令、配置和验证范围 |

单 DP 通过 `python3 test/run_verilog.py --implementation verilog --phase all` 冻结并验证 `DP_verilog_<fingerprint>/`。顶层为 `dp_top`，时钟为 `clock`，复位为同步高有效 `reset`。端口与协议见 [DP 接口](../../src/spec/dp/interface.md)。

DC 使用 [显式约束](../dc_syn/README.md) 定义时钟周期、IO 延迟和负载。DP 的 `clock_port` 必须与 RTL 接口一致。功耗活动与综合网表必须绑定同一个 RTL 指纹和对应层级。

快照与本机 run 由 Git 忽略。先通过 [真实 RTL 门禁](../dc_syn/input-contract.md) 再使用，保留有下游引用的输入和证据。
