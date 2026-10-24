# BF16 最小 DC 验收示例

设计是 Bf16SignPipe：16-bit BF16 输入，一层寄存器，valid 时透传或翻转 sign；reset 和气泡时数据保持。功能与验收见 [spec](../../../spec/bf16_sign_pipe_example.md)。这只验证工具链，不是乘加器/阵列，不用于推导目标浮点算力的成本。

源模板 `Bf16SignPipe.sv.in` 受 Git 管理，公共脚本逐字节导出唯一实际 RTL 到 hw/rtl。手写源的 module_map 明确 source_language=systemverilog、chisel_class=null，门禁同时核对模板与导出字节；原有 Chisel 映射保持兼容。

从仓库根执行完整真实流程（会调用 Icarus 与 DC，须有本次任务授权及可用的挂载环境）：

```bash
python3 scripts/dc_example.py run \
  --technology hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json \
  --constraints hw/dc_syn/constraints/reference-1410mhz.json \
  --machine hw/dc_syn/configs/machines/machine.local.json
```

分步查看 RTL 和功能验证：

```bash
python3 scripts/dc_example.py export
python3 scripts/dc_example.py verify --export-id "$export_id"
python3 scripts/rtl_gate.py "$export_id"
```

每次生成新 export ID。SV 回归穷举 65536 编码 × 两种 negate，另含定向、随机、复位和气泡。独立 Python 参考生成期望向量；只有真实 testbench 成功、周期/数值/保持检查通过且计数和指纹一致，脚本才写 passed 回执。仿真可执行文件自动删除，源 RTL、输入向量和日志保留。

| 产物 | 路径 |
| --- | --- |
| 唯一设计 RTL / manifest | hw/rtl/Bf16SignPipe__.../ |
| SV 验证与总体流程记录 | hw/test/runs/rtl-Bf16SignPipe__.../verification.json、flow.json |
| 官方报告 / 摘要 | hw/dc_syn/runs/dc-Bf16SignPipe__.../reports、summary.json、REPORT.md |
| 功耗所需网表 | 同一 DC run 的 netlist/Bf16SignPipe_mapped.v、SDC、DDC |
| 可提交的精简验收结果 | hw/dc_syn/records/，不带机器私有路径 |

preflight 失败时不启动 DC，flow 的 area/setup/hold 保持 null；综合完成但时序 FAIL 时保留实测面积与负 slack，不放宽约束。完整数据仍须通过 source/export/verification/run 指纹链核验。这个示例未执行真实负载功耗或 RTL/netlist 等价性验证。

## 2026-10-24 真实验收结果

最终代码已通过独立 SV 回归和 DC X-2025.06 综合。工艺为 N22 TT 0.9 V/85°C，目标 1410 MHz，周期 0.709219858156 ns。以下是实际报告提取值，不是解析估算：

| 项目 | 实测结果 |
| --- | --- |
| RTL 回归 | PASS；132423 周期、131867 有效结果、548 气泡、8 复位周期 |
| 穷举覆盖 | 65536 种 BF16 编码 × 两种 negate |
| 总标准单元面积 | 42.630 µm² |
| 组合 / 时序单元面积 | 13.916 / 28.714 µm² |
| 映射单元 | 36 个：19 组合、17 时序；未解析叶单元 0 |
| Setup | PASS；最差路径 slack +0.252183408 ns，违例 0 |
| Hold | PASS；最差路径 slack +0.001825884 ns，违例 0 |
| 未约束检查 | checked_clean |
| 软件回归 | Python 3.6.8 / 3.11 下 16 项通过 |

完整 ID、输入/报告/网表 hash、工具版本和限制见 [精简记录](../../records/bf16_sign_pipe_smoke_20261024.json)。本机 PDK 最初因 Kerberos 票据过期不可读，用户授权 kinit 后恢复；密码和私有路径均不提交。最终 run 清理了 4833144 字节工作缓存，保留 mapped Verilog/SDC/DDC 与原始报告，清理后指纹检查仍通过。

本结果只证明此符号流水级在上述 ZeroWireload 条件下通过逻辑综合验收，不代表布局布线结果或浮点 MAC/阵列的面积、功耗、吞吐。
