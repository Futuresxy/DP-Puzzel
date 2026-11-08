# 多精度 lane 精度寄存器门控验证

基线：`ff9c8ed`，工作分支 `feat/dp-verilog-v14`。源码范围：`dp_lane.v`、`dp_lane_unpack.v`、`dp_lane_operand_unpack.v`。保持算术、group 接口、L8/II=1 及 CModel 不变；不增加 E lane 或独立加法树。

- RTL 快照：`DP_verilog_a32ed7ef4b093ffa`；参数 K16/28/40。
- 全量回执：`test/runs/verilog/20261108T063108307834Z/verification.json`。11 格式 10747 笔默认输出逐位匹配；六组参数检查 2922 笔输出、231654 个流水断点，并检查气泡、非法类型、复位取消。
- 补充回执：`test/runs/verilog/precision_gating_20261108T063107Z/precision_gating.json`。LOCAL_W=27/28/32，每组发送所有 11×11 有序精度组合及零输入，插入气泡/复位（每组363笔接受、334笔完成、29笔复位取消）；每组另完整检查5288笔 E 编码/HiF4 metadata、抵消、scale/C 边界。合计 16866 笔有效输出、2593338 个流水断点全部通过。复位取消不计数值通过。
- 补充命令：`python3.11 test/run_precision_gating.py --export-id DP_verilog_a32ed7ef4b093ffa`；种子20261108。使用 Verilator 5.030，C++20/coroutines 编译环境。
- CModel 数值结果未修改；MXFP4/NVFP4/HiF4 默认961笔各自数学参考 max ULP=0。补充测试不代替完整 PPA 门禁。

S1 保留 ZERO/FINITE 分类低位，关闭 E 不需要的指数高位/特殊值位；S2 分段保存乘积、精简 HiF4 指数；S3 保持原计算，只按 E 恒零位分段保存。消费端使用同拍 datatype 重构，关闭字段旧值不参与有效运算。

早期补充测试曾因统计函数缺少数学参考字段而退出；数值仿真本身通过。已修复测试入口并以上述完整成功回执为准。旧独立 E 通路草案已退出源码，保留本地归档。

功能验证不等于综合时序或功耗证据；后端结果单独记录。
