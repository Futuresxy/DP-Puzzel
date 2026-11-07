# QE 首轮面积优化：功能验收 v1.7.3

日期：2026-11-08T07:37:16.539963+08:00。基线 `a9b4c22`，CModel 检查点 `2aa89c4`。

优化顶层 `dp_top_t8h16q64e128_opt`：固定字段 QE 解包、S1 配对分类/符号摘要、扩展源浮点专用选择。保持全部七种 Q/E、基础 T/H/INT8、L8/II=1、默认 28/40。S3/S4/scale/舍入算术未改。原顶层静态参数为 0，保留原解包与整数选择。

CModel 通过配置别名复用 MixedQE128 的位精确算法；S1 物理寄存内容另由新旧 unpack 对照验证，不将算法 trace 冒充新 S1 寄存布局。

| 版本 | 验证 run | export | S5–S7 断点 |
| --- | --- | --- | ---: |
| optimized | `20261107T233427568086Z` | `DP_verilog_t8h16q64e128_opt_e2fd4e3328a69a69` | 315339 |
| reference | `20261107T233427565517Z` | `DP_verilog_t8h16q64e128_f592ebd6af097577` | 315339 |

两版本各 10747 笔固定数据、三组窗口各 5377 笔有效输出全部通过；每组混合测试 accepted=5841、reset_cancelled=464、cycles=7063。取消项由同步复位作废，不纳入数值比较。14 个 campaign 的输出 SHA-256 均与参考版本一致。

原生 Q64 四子型各 961 笔，max_ulp=1；三种 E128 各 961 笔，math_exact=961、max_ulp=0。全固定 corpus 最大 3 ULP（BF16）；完整逐格式统计见同名 JSON。

新旧解包独立对照 319488 次：四种 Q 的全部字节编码对，三种 E 的全部 nibble 编码对和 64 组双侧 e1/e2，再加 8192 次固定种子随机换型/气泡/复位保持。数值字段、product_negative、product_active、special、all_negative 全部一致。初次 TB 使用 Verilog-2005 不支持的 $fatal，编译未运行；改为 TB 的 $display/$stop 后重新编译并通过，不是 DUT 数值失败。

构建工具：CMake 3.28.4、Verilator 5.030；Verilator 编译使用 GCC toolset 10，CCACHE_DISABLE=1，CXXFLAGS="-std=c++20 -fcoroutines"。

```sh
.deps/cmake-3.28.4/bin/cmake --build src/cmodel/build -j4
python3.11 -m unittest discover -s test/tests -p test_mixed_frontend.py
python3.11 test/run_mixed_verilog.py --frontend t8h16q64e128_opt
python3.11 test/run_mixed_verilog.py --frontend t8h16q64e128
python3.11 -m unittest discover -s hw/dc_syn/tests -v
python3.11 scripts/rtl_gate.py DP_verilog_t8h16q64e128_opt_e2fd4e3328a69a69
```

独立 unpack 对照：选用上述工具环境，运行 `verilator --binary --timing -j 4 --language 1364-2005 -Wno-WIDTH -Wno-TIMESCALEMOD -Wno-INITIALDLY --top-module dp_qe_unpack_equivalence_tb --Mdir /tmp/dp_qe_unpack_equivalence_build -f src/verilog/files_t8h16q64e128_opt.f test/rtl_tb/dp_qe_unpack_equivalence_tb.v`，再执行生成的 `Vdp_qe_unpack_equivalence_tb`。

CModel 五项测试、DC 流程 40 项测试、bash 语法检查通过。功能通过不等于 PPA 通过，综合使用上述优化快照的真实门禁。

## 新增/修改 RTL 的风格自检

| 项 | 结果 | 范围/依据 |
| --- | --- | --- |
| 无魔鬼数字 | 通过 | 固定编码查表注明值含义，布局/宽度使用现有宏和派生参数 |
| define 仅在 .vh | 通过 | 未新增 .v 宏 |
| 组合 assign | 通过 | 新 decoder/unpack/选择均为 assign/generate |
| 显式按位布尔 | 通过 | 先比较或归约；固定配置仿真检查为既有例外 |
| 显式索引/MUX | 通过 | 仅 generate 常量槽索引，格式使用明确选择 |
| DFF 时序 | 通过 | S1 使用生产 DFFE，无功能层 posedge |
| 单信号声明 | 通过 | 普通端口逐行，DFF 固定端口紧凑两行 |
| 复位/寄存类型 | 通过 | 有效位仍由原父层同步低有效复位，payload 无复位 |
| 功能命名 | 通过 | dp_ 文件/module、g_ 展开、ff_s0_s1_ 寄存 |
| payload 使能 | 通过 | 所有新 S1 数据按 rst_n & in_valid 更新 |
| 目录边界 | 通过 | unpack/lane/group/top 与 test/hw 分工不变 |
| 无纯宏别名 | 通过 | localparam 为索引与 bias 差推导 |
| 变量表达功能 | 通过 | exponent_field/magnitude/pair_nan 等 |
| 打包就近说明 | 通过 | M16/E10 原接口保持，新摘要独立端口 |
| 字段宏 | 通过 | 沿用 DP_NUM_CLASS/DP_SP/Q 域宽宏，无新增复合私有布局 |

纯 Verilog-2005 严格 lint 对三个窗口全部通过。表中风格审查只覆盖本轮新增/修改部分，不宣称冻结 SV 或未迁移旧模块符合全部新规则。
