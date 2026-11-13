# dp_top v1.8 电气修复后的真实负载功耗

Run：`power_baseline_v18_repaired_1109`；三点全部 PASS。使用 `dc_dp_top_11092301` 修复网表，面积 **16165.122154 µm²**，setup/hold、VT及电气规则均通过；[DC说明](../../dc_syn/records/dp_top_v18_electrical_repair_20261109.md)。

工况：TSMC N12 120a、6T base/LVT，TT/0.7V/85°C、1 GHz、L8/II=1、ICG开启，时钟转换时间0.1 ns。VCS X-2025.06-1、Power Compiler X-2025.06。保持原Qwen3-8B第0层MLP down_proj的1024笔输入及精确数学参考；测量事务256至767发射期间的512 ns。

| 精度 | K | Internal mW | Switching mW | 动态 mW | 静态 mW | 总功耗 mW | pJ/MAC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bf16 | 16 | 11.550629 | 3.636304 | 15.186933 | 0.141321 | 15.328264 | 0.958017 |
| mxfp8_e4m3 | 32 | 12.099865 | 3.759899 | 15.859764 | 0.142235 | 16.001999 | 0.500062 |
| mxfp4_e2m1 | 64 | 8.586151 | 2.469082 | 11.055233 | 0.141386 | 11.196534 | 0.174946 |

动态=Internal+Switching，静态=Leakage；Total保留工具原始累计值，分项末位可能有舍入差异。

与已发布旧精度门控baseline（面积17782.087803 µm²）相比，本次面积降低约9.09%。这是v1.8整套结构优化加电气修复的比较，不能将收益全部归因于仅增加2.064384 µm²的电气修复。

| 精度 | 旧总功耗 mW | 新总功耗 mW | 变化 |
| --- | ---: | ---: | ---: |
| bf16 | 15.672550 | 15.328264 | -2.20% |
| mxfp8_e4m3 | 16.614388 | 16.001999 | -3.69% |
| mxfp4_e2m1 | 12.506405 | 11.196534 | -10.47% |

每点分别重放冻结RTL与新网表：176笔合法初始化+1024笔负载均逐位一致，L8检查通过。三种精度的负载CModel结果相对独立数学参考均1024/1024精确一致、max ULP=0。VCS native SAIF的实际引脚X/Z=0、missing=0；Power Compiler的Nets/Ports/Pins显式注释均100%，逐引脚翻转率和概率一致。SAIF中未映射到DDC的别名警告仍保留原日志，不作为真实叶引脚缺失放行。

CModel源码及可执行文件在并行v1.9开发之前冻结到本地 `hw/power/runs/baseline_v18_reference_1109/`；派生数据保留原始负载身份和数学golden，只重算v1.8模型expected。计划绑定快照manifest、源码和binary hash，不修改历史manifest，不将模型快照本身当作RTL验证通过证据。

结果及所有hash见[JSON](baseline_v18_repaired_1109.json)，表格见[CSV](baseline_v18_repaired_1109.csv)。本轮使用[固定计划](../plans/baseline_v18_repaired_1109.json)，复现时给run_power.py指定该计划和新的run ID。模型、派生数据、原始SAIF、综合网表和详细报告本地保留，旧功耗结果及依赖不删除。

这是综合后零延迟、CTS/布线前功耗；不包含布线寄生或SDF毛刺，不能作为整芯片功耗。与原数据同K比较；跨K比较必须同时看吞吐和pJ/MAC。
