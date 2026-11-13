# DP 规范化迁移验证 · v1.6

在 `feat/dp-verilog-v14`，从 `f5999eacec02fb82dd22e81c558f914daec0968a` 迁移现用 CModel 与纯 Verilog。采用 [RTL style](../../.skill/dp-rtl-code-style/SKILL.md) 和 [命名规范](../../.skill/dp-naming-convention/SKILL.md)，稳定的数学输入 a/b/c、JSON 字段与冻结 SV 不改。精简可机读结果见 [摘要](dp-style-v1.6.json)。本批按普通运行管理，未额外标记重要结果长期保留；当前门禁与本摘要仍引用的输入受保留规则保护。

## 变更与接口影响

- 顶层及子模块使用 `clock`、同步低有效 `rst_n`。输入复位事件需取反接入；CModel `reset_requested` / JSON `reset=true` 仍表示软件复位请求。
- 功能模块的流水全部实例化公共 DFF：控制同步复位、valid/last 每拍推进，payload 无复位且仅有效时更新。源码有 175 个具名 `ff_sN_sM_*` 边界实例（generate 展开前），顺序逻辑只在两个公共 DFF 原语内。
- 功能组合块用 assign/generate；解包、乘法选择、特殊值归约、对齐、RNE 中间量具名。端口和变量逐项声明，普通实例 `u_`，跨模块线表达端点和功能。保留有限位宽、符号/幅值、RTZ/RNE、L8/II=1 和默认 K16/28/40。
- CModel 区分 exponent_field / fraction_field / fractional_bits；State 使用 operands_a、operands_b、group_max_exponents、e_frontend、c_token。E 实现文件改为 lane/lane_e.cpp、group/group_e.cpp。既有 trace 短键是序列化协议，保持兼容。
- TB 通过适配头区分当前/历史层次及复位端口；manifest 明确低有效同步合同，缺失/错误合同被门禁拒绝。DC 优先按 DFF 捕获级识别，保留旧命名解析。功耗说明要求按所选网表版本连接复位。

## 验证结果

| 范围 | 结果 |
| --- | --- |
| CModel 重构前后逐位差分 | 10747 笔结果、672 笔完整 trace、906 个周期响应一致 |
| CModel 主/E --phase all | 两版通过，数学误差与原实现一致 |
| 多精度 RTL | 10747 笔固定输入、六组混合参数通过；每组 accepted=528、checked=487、reset_cancelled=41 |
| E RTL | 三格式各961笔、5288笔定向全部匹配；六组参数各 accepted=144、checked=137、reset_cancelled=7 |
| 断点 | 多精度 231654；E 1106924；均通过 |
| 编译/lint | 每版六组配置 Verilator 5.030 严格 lint；现用 RTL 为 Verilog-2005 |
| 周期/复位 | L8、II=1、连续请求、气泡、非法类型、last、复位取消通过；Icarus 四态检查8项，确认同步触发、复位优先和无效数据保持 |
| 软件与门禁 | CModel 16项；DC/导出34项；包含新 reset 合同拒绝与 S1–S8 DFF 名解析 |
| 历史兼容 | 冻结 SV 源未改；共享 TB 的 legacy 端口/探针分支编译通过，未重跑 SV 数值回归 |

`golden_exact` 是对有限位宽 CModel 的一致性；`math_exact/max_ulp` 是对独立精确数学参考的误差。默认参数下 FP16 max_ulp=1、BF16=3、TF32=1、MXFP8 E5M2=1，其余固定精度集为0；不把硬件与 CModel 一致误称数学零误差。取消计数仅是在复位时丢弃的在途事务。

最终回执：

| 前端 | export ID | run ID |
| --- | --- | --- |
| 多精度 | `DP_verilog_7e706da2d08e5386` | `20261106T041413762570Z` |
| E | `DP_verilog_e_e15e97bed4d92100` | `20261106T041321972556Z` |

中间两次运行虽然数值通过，但在运行期间修改了验证输入，门禁按预期拒绝签发 PPA 资格。完成修改后重跑的上述两份回执才作为当前验收；没有手工改 manifest 放行。源指纹、回执及摘要 SHA-256 见 JSON。

## 复现

按 CModel README 构建（本机使用已有 CMake 3.28.4、Boost 1.83.0、nlohmann_json 3.11.3），然后执行：

```sh
python3.11 test/run_cmodel.py --phase all
python3.11 test/run_cmodel.py --frontend e --phase all
python3.11 -m unittest discover -s test/tests -v
python3.11 -m unittest discover -s hw/dc_syn/tests -v
python3.11 test/run_verilog.py --implementation verilog --phase all
python3.11 test/run_verilog.py --frontend e --phase all
python3.11 scripts/rtl_gate.py DP_verilog_7e706da2d08e5386
python3.11 scripts/rtl_gate.py DP_verilog_e_e15e97bed4d92100
```

本机 Verilator 5.030 通过 VERILATOR 指定，使用 GCC toolset 10、`CCACHE_DISABLE=1`、`CXXFLAGS='-std=c++20 -fcoroutines'`。格式化使用 Verible v0.0-4298-g085eef05、clang-format 18.1.8。临时 DFF TB、差分脚本与日志在多精度 run 的 auxiliary/，不加入源码测试集；未提交工具、二进制、PDK 或生成 RTL。

## RTL 逐项自检

| # | 检查 | 结果 | 范围/说明 |
| --- | --- | --- | --- |
| 1 | 无含义不明常数 | 通过 | 编码/位宽用格式宏及派生参数；FP4 编码表、阶段编号有明确含义 |
| 2 | define 只在头文件 | 通过 | DUT 常量在 dp_defs.vh；TB 层次适配在 .vh |
| 3 | 功能组合 assign | 通过 | 无功能 always @*；保留纯类型/算术 helper 函数 |
| 4 | 条件显式归约后按位组合 | 通过 | 功能路径无 &&/逻辑非；参数合法性 initial 检查不属于功能网 |
| 5 | 无动态多维数组隐式选择 | 通过 | 数组为常量/genvar 索引，编码选择显式表达 |
| 6 | 时序使用 DFF 实例 | 通过 | 顺序块仅存在于两个公共原语 |
| 7 | 每条声明一个信号 | 通过 | 维护 DUT 的端口/parameter/localparam/变量逐项声明 |
| 8 | 寄存器类型正确 | 通过 | 控制 RU/RE，payload E；同步复位、优先级检查 |
| 9 | 命名规范 | 通过 | 消除裸局部 a/e/f，u_/ff_/g_ 与角色索引；稳定接口例外保留 |
| 10 | 多位 payload 使用使能 | 通过 | rst_n 与所属 valid 限定更新，气泡时保持 |
| 11 | 目录职责 | 通过 | src 开发、test 验证、hw 快照/分析；未改冻结 SV |
| 12 | 无纯 localparam 别名 | 通过 | 保留 signed 位宽转换常量，它们承担显式数值类型约束 |
| 13 | 本地功能与跨模块端点可读 | 通过 | group/lane/align 连线与局部运算变量区分 |
| 14 | 打包布局与解包邻近 | 通过 | S1 atom 固定容器与展开保持在 dp_lane_unpack；其余字段独立保存 |
| 15 | bit-field slice 有布局定义 | 通过 | Number/Special 与 scale/E 字段集中在头文件；参数化切片保留推导 |

自检是上述维护范围的源码审查与功能验证，不是形式等价证明。此次组合表达和 DFF 层级变化可能影响综合优化；**未重新执行 DC、STA 或功耗测量**，不能据此宣称面积下降、功耗下降或频率达标。历史 N12 证据继续只绑定原快照。
