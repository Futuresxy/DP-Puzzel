# DP 功能分区与注释验证 · v1.6.1

基于 `feat/dp-verilog-v14` 的 `33c8a77b0ae2cd5b6a3d1e3499f0ec7b197c92c5`，整理主要计算模块。遵循 [RTL style](../../.skill/dp-rtl-code-style/SKILL.md) 与 [命名规范](../../.skill/dp-naming-convention/SKILL.md)。源指纹、回执/摘要 SHA-256 和各项计数见 [机器可读摘要](dp-functional-blocks-v1.6.1.json)。本批是普通验证，未标记为重要实验；当前门禁和本文引用的证据按保留规则保护。

## 变更

- 多精度 `dp_lane_align` 完整封装 S3 的 E pair、幅值窗口落位、四路 RTZ 及符号恢复；对应 `dp_lane` 的 S3 DFF 不动。抽取正文在端口替换后，与基线计算 token 完全相同。
- E lane 的 S2 pair 复用 N=2 的 `dp_sum_tree`，保留 signed9→signed10 扩展；S4 的先扩展、后精确左移封装为 `dp_lane_e_shift`，仍由 group 的 S4 捕获组和。
- lane/group/top 按 S1 解包、S2 产品、局部规约、scale/LZD、S6 全局对齐、S7 树及 S8 RNE 标注功能区。说明符号旁带、增长位、补零坐标、截断、零/特殊分类和 DFF 所有权。
- 除两个 lane 的组合封装外，19 个修改的既有 RTL 文件剥离注释/空白后 token 不变。两份新模块加入相应显式 files.f。CModel、TB、数值规格、DFF、同步低有效 rst_n、L8/II=1 保持；冻结 SV 未改。

## 验证

| 范围 | 结果 |
| --- | --- |
| 多精度固定向量 | 10,747 笔与有限位宽 CModel 逐位一致 |
| E 固定向量 | MXFP4/NVFP4/HiF4 各 961 笔逐位一致；数学 max_ulp=0 |
| E 定向 | 5,288 笔全部一致；数学 max_ulp=0 |
| 参数与协议 | 两前端各 6 组 K4/K8/K16 和窗口变体，连续输入/气泡/复位/非法元组/last/L8/II=1 通过 |
| mixed 计数 | 主路每组 accepted=528、checked=487、reset_cancelled=41；E 每组 144/137/7 |
| 数值断点 | 多精度 231,654；E 1,106,924，全部匹配 |
| 严格 lint | 两前端各配置通过 Verilator 5.030；Verilog-2005 |
| 真实回执门禁 | 两份新 export 完整回归后由入口签发，再独立校验通过；没有手改 manifest |

主路默认参数 K16/28/40 的数学误差：BF16 max_ulp=3，FP16/TF32/MXFP8 E5M2=1，其余浮点固定集为0；INT8 为逐位精确检查。`golden_exact` 与 `math_exact` 分别代表有限位宽 CModel 和独立数学参考，不能混淆。复位取消的是在途请求，并非漏跑固定向量。

| 前端 | export ID | run ID |
| --- | --- | --- |
| 多精度 | `DP_verilog_5a8854a2656d8cdc` | `20261106T045502464176Z` |
| E | `DP_verilog_e_57dbc8108c448f61` | `20261106T045502462591Z` |

本次未运行 DC/功耗，功能通过不授予旧 PPA 数值。CModel 计算和测试入口未改，使用已构建的同一 CModel 作为参考。

## 复现与产物

```sh
python3.11 test/run_verilog.py --implementation verilog --phase all
python3.11 test/run_verilog.py --frontend e --phase all
python3.11 scripts/rtl_gate.py DP_verilog_5a8854a2656d8cdc
python3.11 scripts/rtl_gate.py DP_verilog_e_57dbc8108c448f61
```

工具环境：Verilator 5.030、GCC toolset 10、CXXFLAGS=-std=c++20 -fcoroutines、CCACHE_DISABLE=1，VERILATOR 指向安装的工具；使用 Verible v0.0-4298-g085eef05 排版。源码阅读顺序见 [模块层级](../../src/spec/dp/dptop/module-hierarchy.md)。结束后仅释放本次两轮的 Verilator 临时 C++/对象/二进制，保留输入、compile/lint/simulation 日志、输出、断点和回执，重新核验门禁。运行保留入口另行预览，重要历史记录不清理。

## 逐项自检（本次修改范围）

| # | 检查 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | 常数含义 | 通过 | 新块位宽由参数/宏派生，N=2 明确是两项 pair |
| 2 | define 位置 | 通过 | 新模块不定义宏，引用 .vh |
| 3 | 组合 assign | 通过 | assign/generate 和组合子模块 |
| 4 | 条件按位组合 | 通过 | 条件先归约；无新增逻辑布尔运算符 |
| 5 | 显式选择 | 通过 | 常量/genvar 切片；无动态多维数组选择 |
| 6 | DFF 保存 | 通过 | 父层全部 DFF 及捕获边界未改 |
| 7 | 单变量声明 | 通过 | 端口重复完整类型，逐项声明 |
| 8 | 寄存器类型 | 通过 | 无新增状态，原控制复位/数据保持语义不变 |
| 9 | 命名 | 通过 | dp_/u_/g_，in_sum/in_shift/out_sum 等语义命名 |
| 10 | payload 使能 | 通过 | 原 DFFE 与 valid 关系未改，协议回归通过 |
| 11 | 目录 | 通过 | lane 封装、算术共用、显式文件清单；SV 冻结 |
| 12 | localparam | 通过 | 无新增纯别名 |
| 13 | 功能信号名 | 通过 | products/exponents/leaves/extended_sum 明确数值含义 |
| 14 | 打包解包 | 通过 | 同类元素扁平 bus 按参数切片；pair 宽度/顺序明确 |
| 15 | 字段切片 | 通过 | E/Q 路数、产品/指数宽使用宏，窗口使用参数 |
