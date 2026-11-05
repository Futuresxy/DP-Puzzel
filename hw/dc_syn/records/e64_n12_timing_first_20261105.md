# E64 全局对齐复核与时序优先综合

**结果：数值复核通过；同一 RTL 仅关闭显式面积回收后，1GHz setup/hold 与 LVT 配额均通过。** 运行于2026-11-05 23:54–23:59（+08:00），记录整理于2026-11-06。

本轮在 `feat/dp-verilog-v14`、基线 `2fac053` 上，按用户要求先排查 E-only 数值逻辑，再保持 RTL/L8 不变做 DC 时序优化。验证快照仍为 `DP_verilog_e_13931c818a591220`；不修改 RTL、CModel、流水、功能输入或测试通过状态。

## S5 坐标与 S6 移位复核

E64 的 HiF4 e2 已在 lane 内消费，S5 宽度 M31 的小数点为 F19，原多精度 HiF4 为 F21。不能只替换乘积而保留旧 anchor；当前实现已同步更新三元组 magnitude/anchor/z。

令 `alpha=scale_exp_a+scale_exp_b−254`。E 组在 S4 统一 F4；MX 旁路14位幅值低补17零，S5 F21，anchor=alpha+9；NV/HiF 22位无符号乘积低补9零，S5 F19，anchor=alpha+11。对应 `src/verilog/group/dp_group_e.v` 和 `src/cmodel/lib/group/e.cpp`。

`dp_top_e.v` 将组 M31 幅值低补8零到 M39，C 的 M32 幅值低补7零到 M39，anchor/z 原样传递。低补零增加 F 和 M 同样的位数，因此不改变 anchor 和非零源的 LZD 计数。C 仍使用相同的 FP32 解包。

共享 `dp_global_align.v` 不按浮点 datatype 选择固定 F；它计算：

```text
value = (-1)^sign * magnitude * 2^(anchor-(M-1))
e = anchor-z
E_max = max_active(e_group0, ..., e_group3, e_C)
net = anchor-E_max
aligned = (magnitude << (39-M)) << net  # net<0 时为 unsigned RTZ 右移
```

HiF4 非零有限组令 k=2−r（原多精度公共元素指数 r∈0..2）：m_old=m_E<<k，A_E=A_old+k，z_E=z_old+k。因此 e 不变、E_max 不变、net_E=net_old+k；幅值和移位量的变化相抵，S6 输出相同。原多精度的 datatype 差异已经在前端 token 中编码；E-only 的整数旁路固定关闭符合接口合同。

真实保存向量 `hif4/K64/correct_961`、id=0、group=1 的 trace：

| 项目 | 多精度 | E64 |
| --- | ---: | ---: |
| S5 magnitude | 69730304 | 17432576 |
| A_raw | -21 | -19 |
| z | 4 | 6 |
| e=A_raw-z | -25 | -25 |
| E_max（包含 C） | 1 | 1 |
| net | -22 | -20 |
| S6 aligned TC | 4256 | 4256 |

本例两种实现的五路 S6 结果均为 `[-1820,4256,-2324,7308,307625590784]`。右移量不同是正确坐标转换，而非漏改。零/NaN/Inf 由 active/special 屏蔽；完整 signed11 净差经 dp_bidir_shift 处理，移位量不截短回绕。

本轮重跑 `python3.11 -m unittest discover -s test/tests -p test_e_frontend.py -v`：6 项通过，含三类各961保存向量的 S5 坐标/S6–S8 对照、参数化独立 Fraction 检查、全 nibble/HiF 元数据、scale/特殊值、周期与非法输入。日志保留在本轮 run 的 review 目录。既有完整 Verilator 验证仍由统一门禁重新核验（见 [重要 RTL 回归](../../../test/results/e64-v1.5.8.md)），没有用 CModel 检查替代 RTL 门禁。

结论：本轮审查及已覆盖测试未发现 E64 与 C 对齐的数值错误。S6 的移位逻辑也不在当前 S7→S8 setup 违例的组合路径内；后者经过 S7 sum 寄存器启动，走 abs/LZD/规格化/RNE。

## 综合策略和证据边界

初次重综合只将 `optimize_area` 从 true 改为 false：不请求 `set_max_area 0`，不执行显式 `optimize_netlist -area`。仍执行 compile_ultra、设计规则修复和 hold 修复；工具内部仍可进行正常映射/面积权衡，不能称为完全关闭面积优化。

新配置为 `hw/dc_syn/constraints/dp-1000mhz-timing-first.json`。1ns 周期、setup/hold uncertainty 0.10/0.03ns、IO 延迟/负载、clock gating、层级以及 N12 TT 0.7V/85°C、LVT≤20% 均保持原值。不使用 false path/multicycle/case analysis，不放宽验收。

## 实测结果

正式 run：`dc_dp_top_e_11052354`；原失败基线 `dc_dp_top_e_11052108` 保留不变。两次 resolved.json 的 gate、technology、machine、target_dbs 完全相同，冻结的 DC.tcl 也逐字节相同；constraints 只有 optimize_area 和说明性 ID/purpose 改变。实际工具 DC X-2025.06，库为 TSMC CLN12FFCLL / BWP6T16P96CPD 120a base+LVT。

| 项目 | 原 E64（面积回收开启） | 新 E64（显式面积回收关闭） |
| --- | ---: | ---: |
| 总面积 / µm² | 5545.893928 | 5686.972455 |
| 组合面积 / µm² | 4011.024452 | 4148.564035 |
| 时序单元面积 / µm² | 1534.869475 | 1538.408420 |
| 最差 setup slack / ps | -0.307322 | +0.015974 |
| S7→S8 slack / ps | -0.307322 | +0.239730 |
| 最差 hold slack / ps | +0.609338 | +0.611901 |
| setup / hold | FAIL / PASS | PASS / PASS |
| LVT 非 blackbox cell 比例 | 16.16% | 14.95% |
| flow_pass | false | true |

面积增加约2.54%，新全局关键路径位于 S6→S7：`leaves_q_reg_40_` → `sum_q_reg_41_`。S8 最差路径变为 `sum_q_reg_12_` → `out_d_reg_17_`。setup/hold WNS/TNS 均为0、违反路径数均为0；最差正 slack 见表，不能把 WNS=0 误读为精确余量等于零。

| 捕获级 | 最差 setup slack / ps | 通过/检查数据端点 |
| --- | ---: | ---: |
| S1 | +279.435754 | 818/818 |
| S2 | +198.632121 | 478/478 |
| S3 | +174.904406 | 258/258 |
| S4 | +1.041174 | 190/190 |
| S5 | +0.117898 | 204/204 |
| S6 | +0.185192 | 217/217 |
| S7 | +0.015974 | 60/60 |
| S8 | +0.239730 | 35/35 |

共2260个数据端点全部通过，门控寄存另列；无 unclassified 寄存。link/check_design 通过，未解析叶单元0，单时钟、未约束端点检查 clean。DC 门禁与流程软件33项测试、shell语法检查均通过。

这个对照说明，在当前 N12 TT、1GHz 综合约束下，无需修改 E64 数值逻辑或流水即可消除 setup 违例。它不能把原违例精确归因到某一条单元替换/面积优化命令；完整综合的映射及后续 hold 修复也会随策略改变。

与原多精度 28/40 基线 dc_dp_top_11052111 的18029.555835µm²相比，新 E64 小约68.46%。两者工艺/时序/吞吐相同，但显式面积回收策略不同，因此这是时序通过的候选面积与原基线对照，不能称为完全同综合策略的面积比较。原同策略对比仍见 [首轮报告](e64_n12_comparison_20261105.md)。

通过范围为单 corner、ZeroWireload 的综合时序，最紧余量仅0.015974ps；不代表 CTS/布线寄生/多 corner 签核，也不证明1.41GHz。后续若要求实际实现裕量，应另立更严格的优化预算并在原验收预算下复核，不能把当前正余量解释为有充分物理裕量。没有执行功耗或门级等价，power_ready=false。

## 保留与复现

按用户对本批重要结果的要求，本次 run 已写 retain.json；保留 netlist/ 中的 mapped.v、DDC、SDC，以及 inputs/、reports/、logs/、summary.json 和 review/ 内的复核日志。原始大文件只保留本机。新 [精简综合记录](e64_n12_1000mhz_timing_first_20261105.json)、配置和本文进入 Git；原失败记录不覆盖。

```sh
python3.11 -m unittest discover -s test/tests -p test_e_frontend.py -v
python3.11 scripts/rtl_gate.py DP_verilog_e_13931c818a591220
PYTHON=python3.11 bash scripts/dc_syn.sh check \
  --export-id DP_verilog_e_13931c818a591220 \
  --technology hw/dc_syn/configs/technologies/n12-base-lvt-tt-0p7v-85c.json \
  --constraints hw/dc_syn/constraints/dp-1000mhz-timing-first.json \
  --machine hw/dc_syn/configs/machines/machine.local.json
# 使用相同选项 prepare --purpose 'E64 timing-first reproduction'，按打印的新 run ID 执行 run。
PYTHON=python3.11 bash scripts/dc_syn.sh report --run-id dc_dp_top_e_11052354
```

RTL 未变，继续消费原完整 Verilator 的通过证据，不将本次 CModel 审查伪装为一次新的 RTL 回归。
