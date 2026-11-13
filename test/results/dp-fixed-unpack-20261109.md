# dp_top 固定格式直接打包验证（2026-11-09，Asia/Shanghai）

基线提交 `36bbbf5`，分支 `feat/dp-verilog-v14`。新导出
`DP_verilog_ce47b3d5b06c0eca`；纯 Verilog dp_top，K16/LOCAL28/GLOBAL40，L8/II=1。

## 实现边界

新增 `src/verilog/unpack/dp_unpack_atom.v`，每份对应单侧一个 M16/E10/S4 atom。
按格式固定切片、固定拼零及小位宽指数补偿，在原编码上判定 Zero/Inf/NaN/sNaN。
`dp_lane_operand_unpack` 直接保存 atom 输出，不再实例化逐元素通用解码器并二次打包。
生成循环中的字段宽度/位置全部是 localparam，无运行时字段宽度移位/掩码。

S1 payload、分类/sNaN 存储及精度门控不变；特殊值仍在解包内部完成判定，A/B 配对
归约仍在 S2 组合段。没有提前配对摘要或减少寄存位，没有删除 INT8，也没有改变数值
合同、CModel、golden、top 端口或流水。混合顶层中的多精度 lane 会继承更新，但本批
未重新综合其顶层；旧六架构面积/功耗报告保持旧快照，不替换功耗 catalog。

## 功能验收

- CModel 构建成功，Verilator 5.030 严格 lint 通过。
- 完整 `test/run_verilog.py --implementation verilog --phase all`：11 种格式、
  六组 K/LOCAL/GLOBAL 参数全部 PASS，数值、流水、气泡、复位和断点通过。
- 默认配置 10747 个输出与 CModel bit-exact；六组混格式各 checked=487、
  reset_cancelled=41（复位清除在途事务），共 2922 个输出通过。
- 相对数学精确参考的最大 ULP：BF16=3、FP16=1、TF32=1、MXFP8 E5M2=1，
  其余受测浮点格式=0；INT8 精确匹配。未更改误差标准或参考结果。
- 补充新旧解包字段对照 **659200** 笔全部一致：穷举 TF32 的 19 位有效编码、
  FP16/BF16 的 16 位编码，Q/INT 字节编码、E payload 和 HiF4 三位元数据组合，
  同时比较两个 atom 的 M/E/S/class/sNaN。参考模块来自基线 Git 源码。
- RTL 后端门禁通过；验证通过不能代替 DC 时序/面积或真实活动功耗。

验证运行：`test/runs/verilog/20261108T165436428176Z/`，主摘要为
`verilator-verilog-all-summary.json`，门禁回执为 `verification.json`；补充字段对照的
TB、参考模块、日志和校验和位于该 run 的 `unpack_equivalence/`。

复现主验证使用 Python 3.11、Verilator 5.030、GCC toolset 10，
`CCACHE_DISABLE=1 CXXFLAGS='-std=c++20 -fcoroutines'`；先构建既有 CModel，
再执行以上完整回归命令。测试消费新冻结快照，不修改旧导出。

## 综合对照

同约束综合运行 `dc_dp_top_11090056`，对比 `dc_dp_top_11081432`。
N12 TT/0.7V/85°C、1GHz、精度门控及 clock gating 开启，
`dp-mixed-1000mhz-incremental.json`，保持原 IO/uncertainty/层级策略。
最终 flow_pass=true，setup/hold、VT 配额和电气规则均通过。总面积从
17782.087803 降至 16831.217776 µm²（减少 5.3473%），同模块边界的八份
u_lane_unpack 合计从 3364.3193 降至 2375.4792 µm²（减少 29.3920%）。
S1 slack 为 +41.324377 ps；全局 setup/hold 最差余量仅约 +0.032/+0.030 ps，
属于当前 TT 综合通过，不代表布线/多角签核。

S1 RTL 寄存声明不变，但 DC 消除了 E-only 槽位的 32 个恒零 class_high 和
32 个恒零 sNaN DFF，物理 DFF 从 5383 降至 5319，ICG 均为148。
详细边界、逐实例数据与来源见 [综合对照](../../hw/dc_syn/records/fixed_unpack_20261109.md)。
本轮没有测新功耗，保留此前六架构功耗基线。
