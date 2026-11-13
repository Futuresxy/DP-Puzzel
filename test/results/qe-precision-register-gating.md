# QE lane 精度寄存器门控验证

基线提交 `e8e2012`，分支 `feat/dp-verilog-v14`。修改 `dp_lane_qe.v`、`dp_lane_unpack_qe.v` 的 S1–S3 寄存器使能及同拍字段恢复；CModel、算术、S4 输出布局和 L8/II=1 不变。保留用户原有 `dp_group.v` 工作区修改，未纳入本批代码修改。

| 验证 | 冻结快照 / 回执 | 结果 |
| --- | --- | --- |
| Q32E64 完整回归 | `DP_verilog_q32e64_8fc17d1108154f48`；`test/runs/verilog/20261108T082824929343Z/verification.json` | 七种格式各961笔；三组参数混合检查共15585笔有效输出、177591个断点通过 |
| 共享 QE 的混合顶层 | `DP_verilog_t8h16q64e128_opt_5b3970766ee38480`；`test/runs/verilog/20261108T082826078457Z/verification.json` | 26878笔有效输出、315339个断点通过 |
| 连续/复位精度切换 | `test/runs/verilog/precision_gating_20261108T082920Z/precision_gating.json` | 16725笔有效输出、184071个断点通过 |
| Icarus 四态补充 | `test/runs/verilog/qe_precision_gating_four_state_1108/result.json` | 首笔 E 模式，195笔有效输出、2214个断点通过；15笔被复位取消 |

Q32E64 默认原生数据中，E5M2 数学 max ULP=1，其余六种精度=0；6727笔全部逐位匹配 CModel。混合协议每组 accepted=5642、checked=5195、cancelled=447，复位取消不算数值通过。参数为 LOCAL_W/GLOBAL_W=27/40、28/40、32/64。

补充回归每个参数覆盖七种精度的49种有序切换和显式零输入，先连续完成147笔，再气泡/复位完成140笔、取消7笔；另完整检查5288笔 E 编码、HiF4 元数据、抵消、scale/C 边界。种子20261108。四态检查确认关闭字段中未初始化的 X 不进入有效输出。

复现（Verilator 5.030，GCC10，C++20/coroutines）：

```sh
python3.11 test/run_lowp_verilog.py --frontend q32e64
python3.11 test/run_mixed_verilog.py --frontend t8h16q64e128_opt
python3.11 test/run_precision_gating.py --frontend q32e64 --export-id DP_verilog_q32e64_8fc17d1108154f48
```

四态复现脚本与命令保存在对应运行目录。补充检查不替代完整 RTL/PPA 门禁；DC 与功耗结果另行记录。

后端已完成：[1GHz综合](../../hw/dc_syn/records/qe_precision_register_gating_1108.md)、[同负载功耗对比](../../hw/power/records/qe_precision_register_gating_1108.md)。独立 Q32E64 两个功耗点均完成冻结RTL、VCS门级结果匹配及SAIF活动审计。
