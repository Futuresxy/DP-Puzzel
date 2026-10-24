# BF16 最小 DC 验收示例

Bf16SignPipe 对 BF16 数据透传或翻转符号位；一层寄存器，每周期接收一个有效输入，复位或气泡时保持数据。源模板为 Bf16SignPipe.sv.in，[规格](../../../spec/bf16_sign_pipe_example.md) 与硬件配置受版本管理，实际 .sv 只保存在 hw/rtl 的导出目录。它用于验收综合流程，不作为浮点 MAC 或阵列成本基线。

## 综合

先按 [hw/test 说明](../../../test/README.md) 导出并完成真实 RTL 验证，取得明确的 export ID。本目录不保存 testbench、精度测试脚本或测试配置；DC 只读取已通过门禁的 RTL。

本机库与工具绑定已配置、挂载有效且任务授权实际 DC 时，从仓库根运行：

```bash
bash scripts/dc_syn.sh prepare --export-id "$export_id" \
  --technology hw/dc_syn/configs/technologies/n22-tt-0p9v-85c.json \
  --constraints hw/dc_syn/constraints/reference-1410mhz.json \
  --machine hw/dc_syn/configs/machines/machine.local.json \
  --purpose 'BF16 符号流水级：验收门控、层级保留和综合流程'
# run_id 使用 prepare 打印的名称。
bash scripts/dc_syn.sh run --run-id "$run_id"
bash scripts/dc_syn.sh report --run-id "$run_id" \
  --record bf16_sign_pipe_smoke_20261024.json
```

默认开启 clock gating、最小位宽为 4，保留模块层级和 PE 子树。展开深度、模块 reference 和实例路径在 constraints.hierarchy 中选择，见 [DC 说明](../../README.md)。示例自身没有 PE 阵列；真实 PE 面积分解需要使用含 PE 的设计。

## 当前验收结果

2026-10-24 的唯一保留示例 run：`dc_Bf16SignPipe_10241850`。DC X-2025.06、N22 TT 0.9 V/85°C、1410 MHz（周期 0.709219858156 ns）。

| 指标 | 实测值 |
| --- | ---: |
| 总面积 | 42.434 µm² |
| 组合面积 | 12.250 µm² |
| 时序单元面积 | 30.184 µm² |
| Setup slack | +0.323671222 ns，PASS |
| Hold slack | +0.000076666 ns，PASS |
| 工具插入的时钟门控单元 | 1 |
| 受门控寄存器 | 16 / 17 |

未约束检查 clean。上游 RTL 回归为 132423 周期、131867 有效结果、548 气泡和 8 复位周期，覆盖全部 BF16 编码与两种符号操作。核心数据见 [records JSON](../../records/bf16_sign_pipe_smoke_20261024.json)。

| 产物 | 路径 |
| --- | --- |
| 唯一设计 RTL | hw/rtl/对应 export/src/Bf16SignPipe.sv |
| 上游验证回执 | hw/test/runs/对应 verification/verification.json |
| 综合报告和网表 | hw/dc_syn/runs/dc_Bf16SignPipe_10241850/reports、netlist |
| 综合摘要 | 同 run 的 summary.json、REPORT.md |

当前 PR 只保留这份工作流定义与最新示例产物，已删除被替代且无下游引用的旧示例 run、RTL 导出及验证输出。clean 仅清除 work 缓存；当前网表、SDC、DDC 和原始报告保留。尚未执行布局布线、真实负载功耗或 RTL/netlist 等价性验证。
