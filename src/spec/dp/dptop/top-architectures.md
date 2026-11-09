> 功能：六种 DP 架构相对基线的修改点和代码/spec导航；范围：六种架构入口、dp_top_e兼容入口与top/common复用模块；版本：v1.9.1；修改时间：2026-11-09 23:40:33 +0800；对应代码：src/verilog/top/下七个顶层、src/verilog/top/common/下共用核心与对齐模块；CModel入口src/cmodel/lib/json_io.cpp。

# 六种架构、七个顶层入口

六种架构包括原 `dp_top`，另保留 `dp_top_e` 参数化兼容入口，所以 `src/verilog/top/` 根目录共七个 `.v` 文件。`dp_top_t8h16q32e128` 与 `dp_top_t8h16q64e128_opt` 分别扩展 E 和 Q/E，**两者均保留**；未优化的 `dp_top_t8h16q64e128` 不作为现用入口。

下文采用默认 LOCAL_W=28、GLOBAL_W=40。T=TF32；H=FP16/BF16；Q=MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3；E=MXFP4/NVFP4/HiF4。各模式容量是单笔请求的原生点积项数，不能同时相加。全部保持 L8/II=1，C在DP内部只累加一次。

六种架构的原生可编辑图见 [draw.io 图纸索引](../draw.io/README.md)：分别展示 DP → group → 两条 lane 的嵌套结构、S1–S8 计算分工及基础/扩展参与关系。每种架构独立一个 `.drawio` 文件，重复 group 用叠层与数量标识。

**本批范围：基础dp_top保留v1.8并独立修复DC电气违例；三个混合顶层和Q32E64实施v1.9；E64与dp_top_e保留旧设计。实现、验证与PPA状态分别记录，版本名不等于验收通过。**

三种混合架构的合同见[v1.9](mixed-precision-expansion.md)：E在S3消费e2、LZD22/U31输出；QE在S4消费e2且E旁路Q对齐；S5双指数；2/4扩展组均carry-save合并，双行MUX后唯一CPA。1:2:6为S43，1:2:8和1:4:8为S44。Q32E64复用新版QE，五源CSA后端为S43，见[低精度装配](low-precision-tops.md)。

## 1. 目录与入口

```text
src/verilog/top/
├── dp_top.v                      # 基线 T8H16Q32E64
├── dp_top_t8h16q32e96.v           # 基线 + 2个 E group
├── dp_top_t8h16q32e128.v          # 基线 + 4个 E group
├── dp_top_t8h16q64e128_opt.v      # 基线 + 4个紧凑 QE group
├── dp_top_e64.v                  # 4个 E group
├── dp_top_q32e64.v               # 4个紧凑 QE group
├── dp_top_e.v                    # 兼容：参数化 E16/E32/E64
└── common/
    ├── dp_top_mixed.v            # 三种混合扩展的实现核心
    ├── dp_top_lowp.v             # 两种专用低精度DP的实现核心
    ├── dp_global_align.v         # 全参与源的全局对齐
    ├── dp_mixed_global_align.v   # 带基础/扩展参与屏蔽的全局对齐
    └── README.md
```

filelist依然在 `src/verilog/files*.f`。仿真、导出和综合选根目录中的具体入口，其依赖由清单显式列出；common模块不另算一种容量架构。现有module名保持不变，改变的是文件归属路径。

## 2. 六种架构相对 dp_top 的修改点

| 顶层及源码 | S1–S5前端组成 | T/H/Q/E容量 | INT8 | S6物理源数（含C） | S7总宽 | A/B各宽 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [dp_top](../../../verilog/top/dp_top.v) | 4×dp_group | 8/16/32/64 | K32 | 5 | 43 | 256 |
| [dp_top_t8h16q32e96](../../../verilog/top/dp_top_t8h16q32e96.v) | 原4组＋2×dp_group_e | 8/16/32/96 | K32 | 7 | 43 | 384 |
| [dp_top_t8h16q32e128](../../../verilog/top/dp_top_t8h16q32e128.v) | 原4组＋4×dp_group_e | 8/16/32/128 | K32 | 9 | 44 | 512 |
| [dp_top_t8h16q64e128_opt](../../../verilog/top/dp_top_t8h16q64e128_opt.v) | 原4组＋4×dp_group_qe(COMPACT_UNPACK=1) | 8/16/64/128 | K32 | 9 | 44 | 512 |
| [dp_top_e64](../../../verilog/top/dp_top_e64.v) | 4×dp_group_e，替换原多精度组 | —/—/—/64 | 不支持 | 5 | 43 | 256 |
| [dp_top_q32e64](../../../verilog/top/dp_top_q32e64.v) | 4×dp_group_qe(COMPACT_UNPACK=1)，替换原多精度组 | —/—/32/64 | 不支持 | 5 | 43 | 256 |

### 原 dp_top：比较基线

四个多精度group在S5输出token。S6通过dp_global_align对四个组结果和一份C做MAX、净移位、符号恢复；S7五项完整规约；S8做FP32编码或INT32回绕。原group/lane仍支持T/H/Q/E/INT8。原top还允许K_FP16=4/8/16，本表以默认K16比较；其他五种固定架构采用K16兼容规模索引。

入口：[模块层级](module-hierarchy.md)、[逐级流水](pipeline.md)、[逐级S/I/F](../common/stage-formats.md)、[全局对齐](global-align.md)。

### dp_top_t8h16q32e96：只增加 E 算力

保留原四个dp_group，新增两个dp_group_e，每组贡献E16；新增的高128-bit A/B仅用于E。Q/T/H/INT8仍只使用基础四组。

主要变化在顶层：S6从五源变七源，增加扩展支MAX和两路对齐；S7将基础五项的carry-save两行与新增两项做4:2压缩，双行MUX后唯一CPA，完整总宽仍为43。参与标志随请求逐级保存，非E请求旁路扩展MAX/加法并屏蔽扩展特殊值、负零摘要。基础group明确启用已验收v1.8计算。

入口：[混合扩展合同](mixed-precision-expansion.md)，重点看第3节输入分发、第4–6节参与/MAX/规约；新增前端看 [E lane](../lane/dp_lane_E.md)、[E group](../group/dp_group_E.md)。

### dp_top_t8h16q32e128：更多 E group，Q容量保持32

保留原四组，新增四个dp_group_e，高256-bit A/B仅用于E。S6扩为九源，S7扩展四项先4:2，与基础两行再4:2、双行MUX后唯一CPA，总宽增至44，S8相应处理44位总和。T/H/Q/INT8仍走基础支。与E96的主要差别是扩展组数、输入宽度、对齐源数和规约增长位；与优化Q64E128的差别是新增组不处理Q。

入口：[混合扩展合同](mixed-precision-expansion.md) 的E128配置、[E group](../group/dp_group_E.md)。复用核心配置为EXT_GROUPS=4、EXT_QE=0。

### dp_top_t8h16q64e128_opt：同时增加 Q 和 E 算力

保留原四组，新增四个紧凑dp_group_qe，每组支持Q8/E16。因此Q扩为64，E扩为128；T/H/INT8仍为原容量。S6九源、S7总宽44，与E128物理源数相同，但参与条件从仅E变成Q或E。

新增QE组有Q指数计算、公共MAX和局部对齐。优化版使用固定字段QE解包，提前形成配对符号/分类摘要以压缩S1寄存；扩展源使用浮点落位，裁掉扩展支的INT8选择。基础多精度四组保留INT8。参数为EXT_GROUPS=4、EXT_QE=1、OPTIMIZE_QE=1。

入口：[QE lane](../lane/dp_lane_qe.md)、[QE group](../group/dp_group_qe.md)、[混合扩展及优化实现](mixed-precision-expansion.md) 第2、4–7节。对应解包模块为dp_lane_unpack_qe/dp_operand_unpack_qe。

### dp_top_e64：四组全部使用 E 专用前端

将原四个多精度group换为四个dp_group_e，合法类型缩减为三种E；C/D固定FP32。E前端使用窄整数路径：S2乘法＋pair、S3 lane规约、S4组和/符号分离、S5 scale/LZD。保留E64容量，同时省去T/H/Q/INT8前端。

顶层不需要基础/扩展分支和按格式参与掩码；每笔合法请求四组都工作。S6仍五源、S7仍43位，复用浮点后端算术；去掉INT32 C/落位/输出选择。QE_FRONTEND=0静态选择E组。

入口：[低精度顶层](low-precision-tops.md)、[E lane](../lane/dp_lane_E.md)、[E group](../group/dp_group_E.md)。

### dp_top_q32e64：四组全部使用 QE 专用前端

将原四组换为四个紧凑dp_group_qe，仅保留Q/E，容量仍Q32/E64；去掉T/H/INT8。QE保持S2乘积/指数、S3局部对齐或E pair、S4 lane树、S5组和/abs/scale/LZD的计算组织，并采用COMPACT_UNPACK=1。

顶层与E64共用五源浮点后端和控制，S6五源、S7总宽43，C/D为FP32，无扩展支屏蔽。QE_FRONTEND=1静态选择QE组。

入口：[低精度顶层](low-precision-tops.md)、[QE lane](../lane/dp_lane_qe.md)、[QE group](../group/dp_group_qe.md)。

三个混合扩展的基础支直接实例化四个dp_group；C与S6–S8由混合核心统一组织。所有前端在S5交付公共token接口。E前端HiF4可使用不同于多精度/QE的定点坐标，后端以magnitude/anchor/z解释数值，不要求各前端token字段逐位相同。

## 3. 共用核心与兼容入口的职责

| 模块及实际路径 | 职责 / 使用者 |
| --- | --- |
| [common/dp_top_mixed.v](../../../verilog/top/common/dp_top_mixed.v) | E96、E128、优化Q64E128三种固定包装的完整实现核心，包含group装配、C流水、带参与屏蔽的S6–S8 |
| [common/dp_top_lowp.v](../../../verilog/top/common/dp_top_lowp.v) | E64/Q32E64两种包装的完整实现核心，静态选择E/QE组，组织C与五源浮点后端 |
| [common/dp_global_align.v](../../../verilog/top/common/dp_global_align.v) | 基线、兼容E、lowp核心使用的组合对齐模块；顶层持有S6寄存器 |
| [common/dp_mixed_global_align.v](../../../verilog/top/common/dp_mixed_global_align.v) | mixed核心使用的组合对齐模块；处理基础/扩展MAX及逐源参与屏蔽，核心持有S6寄存器 |
| [dp_top_e.v](../../../verilog/top/dp_top_e.v) | 原参数化E-only完整实现：K_FP16=4/8/16对应E16/E32/E64，保留兼容回归和历史实验入口 |

带容量名称的五个新top是薄包装，静态选择共用核心的配置；包装不增加流水。dp_top与dp_top_e自身是完整实现。dp_top_e64默认数值合同与dp_top_e的E64配置相同，但现有代码分别由lowp核心和旧参数化top组织，彼此没有实例化关系。

代码复用表示共用定义，各实例仍是独立硬件。六种架构不会在运行时共享同一批乘法器。`mixed`表示基础组加扩展组，`lowp`表示只含低精度组，`e64`明确固定E64容量。

```mermaid
flowchart TD
  BASE[dp_top] --> BG[4 × 多精度group]
  E96[dp_top_t8h16q32e96] --> MIX[common/dp_top_mixed]
  E128[dp_top_t8h16q32e128] --> MIX
  QE128[dp_top_t8h16q64e128_opt] --> MIX
  MIX --> MB[4 × 多精度group + 2/4 E 或 4 QE]
  E64[dp_top_e64] --> LOW[common/dp_top_lowp]
  QE64[dp_top_q32e64] --> LOW
  LOW --> LB[静态选择 4 E 或 4 QE]
  OLD[dp_top_e：兼容参数化入口] --> OB[1/2/4 × E group]
```

## 4. 验证、源码清单和历史证据

| 顶层 | 源清单（src/verilog/） | 验证入口 |
| --- | --- | --- |
| dp_top | files.f | test/run_verilog.py --implementation verilog --phase all |
| dp_top_t8h16q32e96 | files_t8h16q32e96.f | test/run_mixed_verilog.py --frontend t8h16q32e96 |
| dp_top_t8h16q32e128 | files_t8h16q32e128.f | test/run_mixed_verilog.py --frontend t8h16q32e128 |
| dp_top_t8h16q64e128_opt | files_t8h16q64e128_opt.f | test/run_mixed_verilog.py --frontend t8h16q64e128_opt |
| dp_top_e64 | files_e64.f | test/run_lowp_verilog.py --frontend e64 |
| dp_top_q32e64 | files_q32e64.f | test/run_lowp_verilog.py --frontend q32e64 |
| dp_top_e（兼容） | files_e.f | test/run_verilog.py --implementation verilog --frontend e --phase all |

命令的构建环境见 [Verilog README](../../../verilog/README.md) 和 [test README](../../../../test/README.md)。CModel使用已实现的对应profile，共用精确数学reference。

本次恢复E128原实现及入口，四个共用模块只移动路径；没有改变算术、DFF、接口或流水。路径变化会改变export指纹，新EDA运行须重新导出/完整验证，旧manifest和回执不能手工改写。历史证据保持原快照路径：

- 基线/E96/E128：[混合DC比较](../../../../hw/dc_syn/records/README.md#历史记录)。
- 优化Q64E128：[QE优化DC比较](../../../../hw/dc_syn/records/README.md#历史记录)。
- E64/Q32E64：[低精度DC比较](../../../../hw/dc_syn/records/README.md#历史记录)。

这些报告属于各自原始快照，不构成本次目录变更后的新测量。本批不运行DC或功耗分析。

目录整理验证：根目录七个顶层、common四个复用模块的边界检查通过；恢复的E128与搬移的四模块内容逐字节等于来源版本。七个顶层Verilator lint、5项混合CModel检查、41项导出/DC流程门禁软件测试通过。未运行新的完整RTL数值回归或DC；以上检查不替代新export的完整验收。

当前六种架构的最新已测面积、时序与后续功耗输入统一见 [综合汇总](../../../../hw/dc_syn/records/latest_six_dp.md)。旧报告已合并清理，历史分析通过Git版本查阅；E96/E128的源码版本差异与待复验范围在汇总中明确列出。
