# DP v1.9 RTL 与冻结验证

三个混合架构和 Q32E64 已实现并通过独立冻结 Verilator 门禁；基础 dp_top 保持 v1.8，独立 E64 的兼容回归通过。全部保留 L8 / II=1。面积、时序及真实负载功耗由各自 DC / Power Compiler 回执单独验收。

| 架构 | 原生数值笔数 | 数学 max ULP | 流水断点 | 冻结快照 |
|---|---:|---:|---:|---|
| multi | 10747 | 3 | 1095599 | `DP_verilog_d7c8c865ebf856be` |
| t8h16q32e96 | 10747 | 3 | 1468989 | `DP_verilog_t8h16q32e96_8954fff85bd0a51a` |
| t8h16q32e128 | 10747 | 3 | 1960329 | `DP_verilog_t8h16q32e128_4a6980b07b36ba7d` |
| t8h16q64e128_opt | 10747 | 3 | 1865409 | `DP_verilog_t8h16q64e128_opt_337f9288b9f6ee50` |
| q32e64 | 6727 | 1 | 933528 | `DP_verilog_q32e64_862eed2557d6dfb5` |
| e64 | 2883 | 0 | 171759 | `DP_verilog_e64_b41489680453ddf8` |

默认 K16/LOCAL28/GLOBAL40，另验证 LOCAL27/GLOBAL40 与 LOCAL32/GLOBAL64。所有接受事务除同步复位取消者外均输出并逐位匹配 CModel；数学误差单独对 exact golden 统计。

实现边界：

- E：专用解包和8个U4乘法，S2窄pair，S3树后完成e2融合，S4窄组和/abs，S5 U22 LZD并补零输出统一token；ARCHITECTURE_V19默认0隔离旧E64。
- QE：Q使用U5指数和宽对齐；E不参与跨lane MAX，绕过Q移位，在共享树末端完成局部e2融合。延续精度分段寄存门控。
- 组指数：scale解包输出signed8无偏指数，S2 signed9求和，S3 A_raw，S5 compare_exp；移位仍用A_raw，MAX使用compare_exp。
- S6：非参与扩展在MAX/特殊值/负零归约中屏蔽；扩展叶子寄存仅在参与精度更新，读取时遮蔽旧数据。
- S7：基础4:2+C的3:2；E96直接4:2合并2扩展，E128/Q64E128先扩展4:2再合并4:2；双行MUX后唯一CPA。完整S43/S44输出，INT固定[38:7]。
- Q32E64使用新版QE及4:2+3:2+CPA公共后端；E64继续旧S3/S4划分、C LZD和原规约树。

验证增加E pair/S3融合/S4幅值/U22 LZD、QE S3叶子/S4和、S5双指数/S6对齐/S7总和断点，以及QE指数和扩展S6寄存保持断言。新增定向向量包含HiF4九种lane e2组合、scale边界、特殊值、负零、C非正规、失活扩展毒化、逐拍换型/气泡/复位。

辅助CSA边界测试：扩展2/4 × W8/40/64，共12,084笔，覆盖有符号最小/最大值、抵消、随机和双行旁路。Icarus PASS，证据位于 `test/runs/verilog/20261109T155145Z-v19-csa-boundaries/summary.json`。此辅助测试不替代冻结DUT的Verilator门禁。

命令环境：

```bash
export PATH=/opt/rh/gcc-toolset-10/root/usr/bin:$PATH
export CCACHE_DISABLE=1
export CXXFLAGS='-std=c++20 -fcoroutines'
export MAKEFLAGS='OPT_FAST=-O0 OPT_SLOW=-O0'
python3.11 test/run_mixed_verilog.py --frontend t8h16q32e96 --verilator /eda/verilator/v5.030/bin/verilator
# 另两个mixed使用相应frontend；q32e64/e64使用test/run_lowp_verilog.py。
```

Verilator 5.030；具体命令、回执、参数日志及源hash见同名JSON和各verification.json。初轮中的回执因源在运行中改变被门禁正常拒绝；以上最终结果全部在源冻结后重跑并再次通过verify_dp_export，不复用失效门禁。

## RTL 自检报告

| # | 检查项 | 结果 | 说明 |
|---|---|---|---|
| 1 | 无魔鬼数字 | 通过 | 新增计算宽度由参数/宏推导；4基础组、2/4扩展为明确架构合同。 |
| 2 | define只在.vh | 通过 | 生产RTL未新增宏定义；TB编译选择为验证专用。 |
| 3 | 组合逻辑assign | 通过 | 新增MUX/坐标/符号转换均assign或组合算术模块。 |
| 4 | 按位运算符 | 通过 | 功能条件先归约后按位组合，initial参数检查除外。 |
| 5 | 动态数组选择 | 通过 | generate固定索引、固定切片；无运行时多维索引。 |
| 6 | 时序DFF实例 | 通过 | 无新增功能always时序块。 |
| 7 | 单变量声明及DFF两行 | 通过 | 新增RTL逐个声明；DFF固定两行。 |
| 8 | 寄存器类型 | 通过 | valid/membership同步低复位，payload无复位带使能。 |
| 9 | 命名 | 通过 | 新信号表达功能和阶段；旧E兼容探针保留既有命名。 |
| 10 | 多位数据使能 | 通过 | v1.9寄存器按valid；扩展叶子按valid+precision。 |
| 11 | 目录 | 通过 | 共享CSA在arithmetic，顶层复用保持top/common。 |
| 12 | localparam纯别名 | 通过 | 新增参数为推导值或明确坐标偏移。 |
| 13 | 信号语义 | 通过 | A_raw/compare_exp、sum/carry、magnitude/sign分别定义。 |
| 14 | pack后无裸解包 | N/A | 本轮未新增异构结构打包。 |
| 15 | bit-field宏 | 通过 | 沿用DP字段宏；新索引只选择参数化同构算术槽。 |

本表覆盖本次新增/迁移RTL；旧兼容分支保留既有命名和观察接口。独立CModel agent已审查U22/M位LZD等价、Q/E坐标、active、carry位权和MUX配拍，未发现数值/协议阻塞。后续若仅对Q开启group_max寄存器，必须在E消费端显式恢复0，否则旧Q指数会污染E的A_raw。

潜在后续优化：S7扩展合并压缩器仍接收基础两行活动，可在功耗报告显示其成为热点后评估额外操作数隔离；不能仅凭资源数量宣称面积/功耗降低。旧实测与快照均保留。
