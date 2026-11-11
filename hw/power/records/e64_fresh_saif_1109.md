# 原 E64 设计：新一轮真实负载 SAIF/功耗

运行 `power_e64_fresh_saif_1109`，使用原已通过的 `dc_dp_top_e64_11080854` 网表和 `DP_verilog_e64_628e283760c4e830` 冻结 RTL。未迁移 E64 架构、未重新综合。v1.9-capable 模型显式设置 `frontend=e, architecture_v19=false`，保持原数值合同。

| 精度 | K | 面积 µm² | 动态 mW | 静态 mW | 总功耗 mW |
| --- | ---: | ---: | ---: | ---: | ---: |
| MXFP4 E2M1 | 64 | 5644.136492 | 6.980136395 | 0.056096117 | 7.036235809 |

与原测量数值一致。本次重新生成 VCS native SAIF，重新运行 Power Compiler；不是复用旧 SAIF。N12 TT/0.7V/85°C、1GHz、L8/II=1、ICG开启、512ns窗口与其他点一致。48笔合法初始化、1024笔原生K真实负载的冻结RTL和门级重放均通过；数学参考1024/1024精确，max ULP=0。真实叶引脚X/Z及missing均0，Power Compiler显式Nets/Ports/Pins均100%。

[固定计划](../plans/e64_fresh_saif_1109.json)，[精简JSON及证据hash](e64_fresh_saif_1109.json)。源负载和旧PPA依赖均保留。测量是综合后零延迟、CTS/布线前结果，不包括布线寄生或SDF毛刺。
