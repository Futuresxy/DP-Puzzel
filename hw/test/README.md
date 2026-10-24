# 最终验证依据：Verilog/SystemVerilog RTL testbench

直接实例化 hw/rtl 中选定导出的模块，对该份 RTL 做数值精度和周期协议验证。独立参考模型可用其他语言生成向量；最终判定由 RTL 仿真结果形成。Chisel 内部测试只辅助小模块开发。

后续文件职责：

| 位置 | 职责 |
| --- | --- |
| tb/ | 可审查的 Verilog/SystemVerilog testbench、driver、monitor、scoreboard |
| reference/ | 与 DUT 独立的数值参考和向量生成规则 |
| vectors/ | 小型定向向量与真实负载 trace 元数据；大数据外部归档 |
| regressions/ | 按硬件配置/格式/模式定义回归集合 |
| runs/ | 被忽略的仿真中间文件和运行结果 |

验证矩阵必须覆盖：格式合法码/边界、缩放、舍入、溢出、特殊值（按格式规范）、累加误差、block 边界、尾 tile、参数边界、复位、连续 valid、气泡、反压和模式切换。bit-exact 的适用边界与允许误差要在 spec 中固定。

每份通过证据绑定 export ID、RTL 文件 hash、参考语义版本、testbench/向量 hash、工具版本和随机种子；失败、未执行或证据过期均不能进入 PPA。真实负载回放还需核对结果、周期、tile 分配与活动窗口。

设计 RTL 不复制到 test 目录。失效生成 RTL、无用波形、临时 testbench 和仿真可执行文件按引用关系清理，保留必要失败日志和最小复现。当前无测试实现或通过记录。

已实现 [统一证据门禁](../../scripts/rtl_gate.py) 和 [回执 v1 契约](../dc_syn/input-contract.md)，仅核验现有 RTL/验证输入/日志的指纹及精度/周期状态。它不是仿真入口，也不生产通过记录；后续真实回归入口按该契约写证据。
