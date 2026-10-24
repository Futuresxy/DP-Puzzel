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

每份通过证据绑定 export ID、单个 RTL 目录指纹、参考语义、testbench/向量路径、工具版本和种子；不再逐文件写 hash。失败、未执行、RTL 目录指纹不匹配或数值验证输入比回执更新时阻止 PPA。真实负载回放还需核对结果、周期、tile 分配与活动窗口。

设计 RTL 不复制到 test 目录。失效生成 RTL、无用波形、临时 testbench 和仿真可执行文件按引用关系清理，保留必要失败日志和最小复现。已有用户授权的 Bf16SignPipe 例子：tb/Bf16SignPipeTb.sv、reference/bf16_sign_pipe.py，真实回执写入被忽略的 runs；它不是完整研究硬件回归入口。

已实现 [统一证据门禁](../../scripts/rtl_gate.py) 和 [回执 v2 契约](../dc_syn/input-contract.md)，门禁核验目录指纹、输入路径/更新时间及精度/周期状态。hw/test/scripts/bf16_sign_pipe.py 在真实 SV testbench 通过后生产证据，门禁本身不生产 PASS。

例子硬件参数在 hw/configs，测试参数独立放 configs/bf16_sign_pipe.json。测试入口与综合入口分离：

```bash
python3 hw/test/scripts/bf16_sign_pipe.py export
python3 hw/test/scripts/bf16_sign_pipe.py verify --export-id "$export_id"
python3 -m unittest discover -s hw/test/unit -v
```

unit/test_dc_flow.py 只验证流程的软件行为，不调用 EDA。DC 目录不维护另一份 testbench、测试脚本或测试配置。
