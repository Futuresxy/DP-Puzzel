# Q 专用扩展 DP v1.10 验证（2026-11-12）

新增 `dp_lane_q`、`dp_group_q` 及 `dp_top_t8h16q64e64` 完成 CModel、纯 Verilog 和冻结RTL验证。基础四组保持 T8/H16/Q32/E64，额外四个 Q8 组仅参与四种 Q 格式；完整顶层容量 T8H16Q64E64，L8/II=1。S6九源统一对齐，S7默认S44 carry-save规约与唯一CPA，C只计一次。

当前合同：[Q lane](../../src/spec/dp/lane/dp_lane_q.md)、[Q group](../../src/spec/dp/group/dp_group_q.md)、[完整顶层](../../src/spec/dp/dptop/t8h16q64e64.md)。CModel新profile缺省采用当前数值骨架，显式`architecture_v19=false`拒绝；不提供不存在的旧Q-only合同回放。

## 冻结验证证据

- export ID：`DP_verilog_t8h16q64e64_044cfe1be3f22a8d`。
- verification/run ID：`20261112T105255076422Z`；完整回执：`test/runs/verilog/20261112T105255076422Z/verification.json`。
- 工具：Verilator 5.030、GCC toolset 10.3.1、Python 3.11；关闭ccache并显式启用C++20/coroutines。
- 14 campaigns全部通过：11格式共10747笔原生数据逐位等于CModel；三个窗口27/40、28/40、32/64的协议/断点stress通过，共1099635项断点比较。
- 每个stress campaign：PASS cycles=7440 accepted=6152 checked=5661 cancelled=491。
- 精简机器记录：[JSON](q-only-v1.10-20261112.json)，含每格式数学误差、输入/输出hash、run内日志和输入路径。

| 格式 | 原生笔数 | 数学golden完全一致 | 最大ULP |
| --- | ---: | ---: | ---: |
| tf32 | 1053 | 1040 | 1 |
| fp16 | 961 | 949 | 1 |
| bf16 | 961 | 958 | 3 |
| mxfp8_e4m3 | 961 | 959 | 1 |
| mxfp8_e5m2 | 961 | 958 | 1 |
| mxfp6_e3m2 | 961 | 958 | 1 |
| mxfp6_e2m3 | 961 | 960 | 1 |
| mxfp4_e2m1 | 961 | 961 | 0 |
| nvfp4 | 961 | 961 | 0 |
| hif4 | 961 | 961 | 0 |
| int8 | 1045 | 1045 | N/A（整数） |

S3/S4检查Q逐叶及lane规约；S5检查sign/magnitude/A_raw/compare_exp/special；S6检查参与掩码、唯一公共坐标与每路对齐值；S7检查完整规约。Q64数据沿既有K64真实向量和golden，scale的K32块广播保持原定义。E三格式维持K64，未扩展为128。

定向覆盖逐拍Q↔三种E、基础高精度、无效tuple、气泡、同步复位和last；扩展旧NaN/Inf、大scale与全负零毒化；四Q格式和C特殊/非正规边界；NaN E8M0 scale乘±Inf时的S5分类（invalid置位、Inf字段清零）与当前group合同一致。Q乘积寄存器及扩展S6叶子验证无效期间保持。

新CModel专用测试`test/tests/test_q_only_frontend.py`三项通过：缺省当前骨架、拒绝legacy、scale NaN/Inf token分类。完整CModel、原混合顶层兼容回归及统一门禁的批次记录由本报告附录汇总。

## 复现

```sh
source /opt/rh/gcc-toolset-10/enable
CCACHE_DISABLE=1 CXXFLAGS='-std=c++20 -fcoroutines' python3.11 test/run_mixed_verilog.py \
  --frontend t8h16q64e64 --verilator /eda/verilator/v5.030/bin/verilator
```

准备阶段的失败来自只读ccache目录、系统旧编译器缺少coroutine、未启用C++20及缓存构建产物异常；相同冻结输入禁用ccache重建后完整通过。调试构建和失败run不授予验证状态；不复用其结果冒充验收。源码/测试过程中独立review修复了scale NaN×Inf的token分类与新profile缺省旧骨架问题，以上正式回执包含两项修复。

当前仅功能、精度和周期证据；未执行本新增设计的DC、时序或功耗测量，不能声称1GHz/1.41GHz闭合或面积/功耗改善。旧PPA和冻结SV未修改。

## RTL 逐项自检

检查范围为新增 Q 解包/lane/group/顶层及 `dp_top_mixed` 新增的静态 Q 分支；既有未迁移模块不借本次任务重写。

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | 无魔鬼数字 | 通过 | 算术宽度、格式域、bias、scale与特殊值索引使用宏或具名派生参数；4扩展组是固定profile合同 |
| 2 | define 只在 .vh 中定义 | 通过 | 新生产 .v 无 define，复用 dp_defs.vh |
| 3 | 组合逻辑用 assign | 通过 | 新数值计算使用 assign、generate 和组合基础单元 |
| 4 | 无布尔运算符 &&/\|\|/! | 通过 | 功能条件先比较/归约再按位组合；仅非综合参数检查沿用逻辑运算 |
| 5 | 无动态多维数组直接索引 | 通过 | lane 寄存数组仅由 generate 常量 element_index 索引，输出扁平总线 |
| 6 | 时序逻辑实例化 DFF | 通过 | 新生产模块无手写 always 时序块，全部显式库 DFF |
| 7 | 每行一个信号 | 通过 | 端口/变量逐行完整声明；DFF按固定两行，普通模块端口逐行 |
| 8 | 寄存器类型正确 | 通过 | valid 使用同步低有效复位DFF；payload无复位，以有效位屏蔽 |
| 9 | 命名规范 | 通过 | dp_文件/module一致，ff_sN_sM实例，rN寄存，角色索引 |
| 10 | 多bit数据有使能 | 通过 | 所有新payload DFF用rst_n与源级valid使能；Q乘积及扩展对齐寄存hold断言 |
| 11 | 目录结构正确 | 通过 | 现有unpack/lane/group/top、配置、spec和显式files清单 |
| 12 | 无localparam纯别名 | 通过 | 本地参数为宽度、位移或bias差计算，无宏同义副本 |
| 13 | 信号名表达功能 | 通过 | 幅值、指数、分类、anchor、active等明确；A/B保留数学操作数语义 |
| 14 | pack后无裸slice解包 | 通过 | 不新增异构寄存字段包；同类lane/element数组按参数化宽度切片 |
| 15 | bit-field slice使用定义 | 通过 | Q编码域和special字段使用dp_defs宏；无新增硬编码结构域 |

15/15项通过。另核对：各级DFF与计算/旁带就地排列；Q输出S4/S5与既有group同拍；signed/unsigned、RTZ、树增长位和FP32 RNE边界明确；L8/II=1、气泡、同步复位、S3–S7断点由本批冻结RTL验证。仿真结果不构成时序或功耗证据。

## 兼容回归与统一门禁

共享`dp_top_mixed`新增静态分支后，三个原有混合顶层均重新冻结并完成14 campaigns、11格式10747笔原生数据和三个窗口stress；严格RTL来源/回执门禁全部通过。基础dp_top、独立Q32E64与E64生产源码未改，本批不将既有PPA替换为新增结果。

| 顶层 | export ID | verification/run ID | 断点比较数 | 结果 |
| --- | --- | --- | ---: | --- |
| t8h16q32e96 | `DP_verilog_t8h16q32e96_3aa841c911548532` | `20261112T105253439575Z` | 1468989 | 通过 |
| t8h16q32e128 | `DP_verilog_t8h16q32e128_1de697efa0872b22` | `20261112T105014052725Z` | 1960329 | 通过 |
| t8h16q64e128_opt | `DP_verilog_t8h16q64e128_opt_bb3ca2cef7aeb052` | `20261112T105253437676Z` | 1865409 | 通过 |

完整CModel共50项测试通过（包含新Q-only三项、v1.9原生数据/独立有限窗口参考、周期协议与历史合同回放）；DC/RTL门禁软件45项测试通过。这些是软件检查，不是DC综合运行。日志和SHA256见JSON的`software_checks`，原日志保存于新Q run的`auxiliary/`。

按运行保留入口完成预览后，仅清理已结束的本任务环境失败、调试与最终仿真的生成C++、对象、PCH和可执行文件，释放909645710字节；冻结RTL、所有输入/golden/schedule/result/cutpoint、回执与compile/lint日志保留。根目录无参数调试生成的空`dp_results.txt`已删除。清理清单见[JSON](q-only-v1.10-20261112-cleanup.json)，不触及历史PPA或共享ccache。

原混合顶层兼容批次另清理20个已结束build目录，共3110614153字节；本批合计释放4020259863字节。相同保留边界与逐目录清单已合并到上述清理JSON。
