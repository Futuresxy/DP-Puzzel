# v1.9 CModel 验证

三个混合顶层及 Q32E64 使用显式 `architecture_v19=true`；baseline 默认 v1.8、独立 E64 和未开关历史回放保持原合同。数值源指纹、命令及逐格式统计见 [JSON 回执](mixed-cmodel-v1.9.json)。

| 配置 | 完整样本 | 数学逐位一致 | 最大 ULP | 架构失配 |
| --- | ---: | ---: | ---: | ---: |
| t8h16q32e96 | 10747 | 10715 | 3 | 0 |
| t8h16q32e128 | 10747 | 10716 | 3 | 0 |
| t8h16q64e128_opt | 10747 | 10710 | 3 | 0 |
| q32e64 | 6727 | 6724 | 1 | 0 |

47 项单元测试全部通过；baseline 10,747 笔完整兼容回归通过。新测试涵盖 E 全编码/e1/e2、参数窗口、S3/S4/S5 坐标、U22 LZD、carry-save 位权、失活毒化、负零、特殊值、C 非正规数、L8/II=1、气泡和复位。精确数学模型与已有 golden 均未改。

E 在 S3 消费局部 e2，S4 仅窄组和/取幅值；S5 使用 U22 LZD 再低补零输出。QE 使用 v1.8 的 E 窄 pair/共享树/宽移位旁路合同。无偏 scale、S3 A_raw、S5 compare_exp 和 C 无 LZD 用同一显式版本开关；S7 以模 2^W carry-save 两行合并、选择并验证最终有符号 CPA。

定向输入共享入口：`test/cases/mixed_v19.py`。旧 `test_mixed_frontend.py` 继续验证历史默认，新的 `test_mixed_v19.py` 验证显式 v1.9。模型通过仅证明数值/周期模型；RTL 门控、时序、面积及功耗需要后续冻结 RTL 的独立证据。
