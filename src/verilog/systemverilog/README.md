# SystemVerilog 历史参考（已冻结）

用户于 2026-11-05 明确停止同步维护本目录。保留当前 T8H16Q32E64 多精度单 DP 作为历史 SV 参考；后续新功能、修复、参数/流水优化和 E 类专用单元在 CModel 与纯 Verilog 主实现中开发，不再要求修改这里的 SV 源码。本目录保持现有代码和编译清单，不扩展新功能。

| 冻结项目 | 来源 |
| --- | --- |
| Git 基线 | `efa0de3135ec34468af2af25abec9229dd427d10` |
| 架构 / 实现映射 | v1.5 / v1.5.1；包含 S5 14×8 无符号 scale |
| 默认配置 | `dp_top`，K_FP16=16、LOCAL_W=28、GLOBAL_W=40 |
| 容量 / 流水 | T8H16Q32E64，L8，II=1 |
| 历史源码快照 | `DP_systemverilog_baf3d602c9322d86` |
| 源清单指纹 | `baf3d602c9322d86cbec833617cf842a65ec87e5f41239b788567e330ca14309` |

快照指纹涵盖 [files.f](files.f) 中的 SV 文件及当时共用的 Verilog `.vh` 编码头，与既有快照规则一致。历史通过证据仅适用于冻结版本及当时参数/测试环境，不代表当前 Verilog 或未来 E 专用 DP 的行为。

编译从 `parameter/dp_pkg.sv` 开始，module 名与纯 Verilog 相同，必须独立编译。重放历史版本应配套冻结 Git 基线的 CModel、测试台、数据、编码头及工具记录；后续活跃分支更新这些共享输入时，不要求 SV 追随。默认 [回归入口](../../../test/run_verilog.py) 只测试 Verilog，`--implementation systemverilog` / `both` 保留为显式参考选项，不是新功能验收门禁。

现用维护范围和运行说明见 [上层导读](../README.md)，新 E 设计见 [E lane](../../spec/dp/lane/dp_lane_E.md) 与 [E group](../../spec/dp/group/dp_group_E.md)。SV 历史源码不用于证明新实现的时序、面积或真实负载功耗。
