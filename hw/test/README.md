# 最终验证依据：Verilog/SystemVerilog RTL testbench

直接实例化 hw/rtl 中选定导出的模块，对该份 RTL 做数值精度和周期协议验证。独立参考模型可用其他语言生成向量；最终判定由 RTL 仿真结果形成。Chisel 内部测试只辅助小模块开发。

2026-10-24 已确认 [AI 负载数据采集方案](../spec/ai-workload-data.md)：WikiText-2 test 驱动 Qwen2.5-3B 中间层 Q 投影和 Qwen1.5-MoE-A2.7B 中间层一个专家的 down 投影，每个来源 49,152 MAC，两组合计 98,304 MAC。同源数据独立量化到各目标格式，用于数值验证与后续功耗回放。采集尚未执行；人工定向数据和随机数据的生成方案待后续讨论，golden、文件格式与 testbench 按步骤另行确定。

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

设计 RTL 不复制到 test 目录。失效生成 RTL、无用波形、临时 testbench 和仿真可执行文件按引用关系清理，保留必要失败日志和最小复现。当前完整格式回归尚未实现。新增scripts/check_pe_export.py --smoke只对指定基础PE导出做单位scale、−1/0/+1输入的结果坐标与11级valid定向检查；源TB由脚本按确定随机种子生成，run绑定export/RTL/hash/checker/TB指纹。有限通过不标记manifest passed，不允许PPA。
