# 当前六种 DP 精度门控版验证与 PPA 入口

本轮基线提交 `683f7aa`，直接在 `feat/dp-verilog-v14` 工作。三种混合顶层使用共用 `dp_lane` 的精度寄存器门控，Q64E128 优化版的扩展组同时使用已门控的 `dp_lane_qe`。不修改算术、流水和 CModel；保持 K16/LOCAL28/GLOBAL40、L8/II=1。用户已有的 `dp_group.v` 排版修改未暂存。

| 架构 | 冻结快照 | 完整回归 ID |
| --- | --- | --- |
| T8H16Q32E96 | `DP_verilog_t8h16q32e96_300dc85956eabde8` | `20261108T084804171991Z` |
| T8H16Q32E128 | `DP_verilog_t8h16q32e128_703b37f461e5e9c5` | `20261108T084805338509Z` |
| T8H16Q64E128 opt | `DP_verilog_t8h16q64e128_opt_5b3970766ee38480` | `20261108T082826078457Z` |

完整回执位于 `test/runs/verilog/<ID>/verification.json`。各顶层覆盖11种精度的10747笔默认输入，另外测试27/40、28/40、32/64三组位宽的混合精度、气泡、复位和S5–S7数值断点。E96/E128每组 mixed accepted=5833、checked=5369、reset_cancelled=464；Q64E128每组5841/5377/464。复位取消不计数值通过。全部有效结果逐位匹配 CModel；独立数学误差统计见各完整回执。

复现：`python3.11 test/run_mixed_verilog.py --frontend <t8h16q32e96|t8h16q32e128|t8h16q64e128_opt>`，Verilator 5.030、GCC10、C++20/coroutines。

其他三种架构：dp_top 和 Q32E64沿用已验证门控版，分别见 [多精度门控验证](precision-register-gating.md)、[QE门控验证](qe-precision-register-gating.md)；E64保持原专用前端，沿用 `DP_verilog_e64_628e283760c4e830` / `20261108T004627771406Z` 的通过回执。

当前结果统一入口：[六种综合索引](../../hw/dc_syn/records/latest_six_dp.md)、[六种面积与功耗报告](../../hw/power/records/current_six_precision_gated.md)。功耗的冻结RTL与门级逐位匹配、原生SAIF及注释审计独立于上述RTL回归。无引用旧生成结果按本轮用户要求清理；全部旧功耗数据及其DC/RTL/验证依赖保留作对照，删除范围由[维护回执](../../hw/dc_syn/maintenance/precision_gated_six_cleanup_20261108.json)记录。旧精简测试摘要继续保留，但被清理的大产物不再可用。

本轮DC全部通过1GHz。E96直接通过；E128经增量setup/hold修复及同库DFQD1→DFQD4寄存器驱动增强，Q64E128经增量修复通过。最终约束不变，不增加流水、不修改RTL算术。E128单元功能模型归一化hash一致，正式run另行复查全部时序/VT/电气规则，之后三种负载的门级逐位结果及功耗审计均通过。DC流程新增受限的同家族/VT寄存器驱动修复选项，44项流程测试通过。
