# 五种扩展 DP 的主目录最终验证（v1.12）

2026-11-12：五种profile均通过当前源码严格门禁。Q64E64、E192、E256在合入QE公共模型与测试后重新运行完整RTL回归；两个QE的源码/模型/导出/原始完整验证证据按原字节及mtime复制，随后通过主目录严格门禁。

软件验证：CModel 52项全部通过；DC流程45项全部通过；功耗流程74项，73通过、1项因缺少z3跳过。CModel测试在单进程内串行执行，避免共享配置竞争。

每种均为14个campaign、11格式10747笔原生结果；默认K16/LOCAL28/GLOBAL40，另测27/40、32/64。L8、II=1、原子握手、气泡、复位取消、S3–S7断点和精度门控由RTL TB检查。

| Profile | 当前export | 验证ID | 断点数 | 当前严格门禁 |
|---|---|---|---:|---|
| t8h16q64e64 | `DP_verilog_t8h16q64e64_7547c127f790ac6d` | `20261112T125705417567Z` | 1099635 | PASS |
| t8h16q32e192 | `DP_verilog_t8h16q32e192_b677d181f0a29c7f` | `20261112T125705419410Z` | 2967003 | PASS |
| t8h16q32e256 | `DP_verilog_t8h16q32e256_87332acf0b331629` | `20261112T125705422788Z` | 3966411 | PASS |
| t8h16q96e192 | `DP_verilog_t8h16q96e192_1e63c2625d0dd101` | `20261112T122236879949Z` | 2819997 | PASS |
| t8h16q128e256 | `DP_verilog_t8h16q128e256_f8209095129aa89a` | `20261112T122135109358Z` | 3754053 | PASS |

每个profile保留T8/H16/INT8基础能力：TF32 1053笔、FP16 961笔、BF16 961笔、INT8 1045笔均通过。完整各格式逐位/数学误差和各窗口协议计数见JSON。

Q64E64当前源码export为`DP_verilog_t8h16q64e64_7547c127f790ac6d`；原DC/功耗仍绑定`DP_verilog_t8h16q64e64_044cfe1be3f22a8d`及原验证，未用新回执覆盖历史测量依据。其他四profile的源码导出身份保持一致，DC原始验证ID仍按其输入记录定位。

数值和周期通过不等于时序/功耗通过；硬件测量以独立DC/功耗记录为准。

## 证据与重放

- 原始软件/回归日志、主目录门禁输出及交接指纹：[auxiliary](../runs/verilog/20261112T125705417567Z/auxiliary/final_five_v112/)。
- 模型SHA-256：`2ad7541c12aa4218833700599982b79f69e0c541964e3f6590c3cbe617cdc39c`。
- 回归命令：启用 GCC 10 并将 `VERILATOR` 指向 5.030 后，`CCACHE_DISABLE=1 CXXFLAGS="-std=c++20 -fcoroutines" python3.11 test/run_mixed_verilog.py --frontend PROFILE --verilator "$VERILATOR"`。
- 软件命令：`python3.11 -m unittest discover -s test/tests -v`；对应替换目录为`hw/dc_syn/tests`与`hw/power/tests`；`bash -n scripts/dc_syn.sh`通过。
- 只清理本次三份已结束build的1825个编译中间文件，释放1944842142字节；保留全部输入/结果/断点/回执及lint/compile日志，清理后五个严格门禁再次通过。

## 后续 DC 流程验收

上述45项DC流程测试对应本次功能验收时的版本。T8H16Q128E256后续增加可追溯的定点支路缓冲入口，RTL/流水未改；更新后的54项DC流程测试全部通过，原日志与源hash见 `hw/dc_syn/runs/dc_dp_top_t8h16q128e256_11122146/auxiliary/flow_software_validation/`。正式五种DC与15点功耗最终验收见 [DC汇总](../../hw/dc_syn/records/five_expansions_20261112.md)及[功耗汇总](../../hw/power/records/five_expansions_20261112.md)，不以软件测试或内存探测代替硬件测量。
