# 紧凑解包改造与代码对比 · v1.6.4

基线：`feat/dp-verilog-v14` / `461453207b38d24d8a66f798ca4c5a39ed27ef8b`。本次沿用默认 K16/28/40、L8/II=1，同步低有效 rst_n、valid 每拍推进和 payload 使能不变。CModel 和冻结 SV 源码未修改。

## 1. 前后变化

| 项目 | 基线 | 当前 |
| --- | --- | --- |
| lane 解包入口 | A/B 各一个 dp_lane_unpack | 一个 dp_lane_unpack，内部各一个 dp_lane_operand_unpack |
| S1 到 lane 接口 | 每侧 out_numbers[183:0]，8 个通用 Number | 每侧独立 M32 / E20 / S8；特殊分类输出 lane 摘要 |
| 尾数 bank 输入 | 每侧 8×11=88 位，经过 Number 拆字段 | 每侧 32 位，直接选择 M16 中对应精度字段 |
| 指数 bank 输入 | 每侧 8×8=64 位，经过 Number 拆字段 | 每侧 20 位，直接选择 E10 中对应精度字段 |
| 数值译码 | hidden bit、subnormal、Q rebias、FP4/e1 在元素 decoder | 同一次 decoder，分字段输出，后级只选位片 |
| A/B 特殊值配对和 lane 归约 | dp_lane 内部 | dp_lane_unpack 内部，仍在 S2 组合段 |
| S1 payload 声明宽度 | 84 位/侧 | 84 位/侧，原 M/E/S/class/signaling 布局保持 |
| 流水与数值 | S1 解包、S2 乘积/分类、S3 对齐、S4 lane 和 | 保持；S5–S8 与数值截断不变 |

**184 位旧接口是组合展开连线，不能把这次接口收窄计为寄存器或综合面积减少。** 当前入口输出包含两侧 M/E/S 共 120 位，以及乘积符号 8、活动掩码 8、分类 4、all_negative 1 位；这些字段所属 S1/S2 组合阶段分别标明，未新增寄存级。

```text
之前：元素 decoder → S1 紧凑保存 → 展开 8×Number → lane 再拆字段 → bank
现在：元素 decoder → S1 紧凑保存 ┬→ M32 → 尾数 bank 按格式选位片
                               ├→ E20 → 指数 bank 按格式选位片
                               └→ 符号/class → A/B 配对 → lane 分类摘要
```

## 2. 从这些代码开始查看

| 源码 | 建议查看的内容 |
| --- | --- |
| [dp_lane_unpack.v](../../src/verilog/unpack/dp_lane_unpack.v) | 明确 A/B 尾数、指数、符号输出；g_pair_class 和特殊值归约 |
| [dp_lane_operand_unpack.v](../../src/verilog/unpack/dp_lane_operand_unpack.v) | 单侧紧凑打包、r1_* 字段和就地 S1 DFF |
| [dp_operand_unpack.v](../../src/verilog/unpack/dp_operand_unpack.v) | 原编码分类、hidden bit/subnormal、Q 重编码与数值占位 |
| [dp_mantissa_bank.v](../../src/verilog/lane/dp_mantissa_bank.v) | 直接取 M16 位片；保留两套 HH/HL/LH/LL 资源及重构 |
| [dp_exponent_bank.v](../../src/verilog/lane/dp_exponent_bank.v) | H 取低 8 位、Q 取两组 5 位、HiF4 取共享 e2 |
| [dp_lane.v](../../src/verilog/lane/dp_lane.v) | 紧凑接口互联、S2 捕获及原 S3/S4 计算顺序 |

每个 M16 atom 的当前位片如下；FP16/TF32 没有额外低位补零。

| 格式 | 幅值字段 | S / I / F（独立符号） |
| --- | --- | --- |
| TF32 / FP16 | M[10:0] | 1 / 1 / 10 |
| BF16 | M[7:0] | 1 / 1 / 7 |
| MXFP8 / MXFP6 | M[3:0]、M[7:4] | 每项 1 / 1 / 3 |
| MXFP4 / NVFP4 | 四个连续 nibble | 每项 1 / 3 / 1 |
| HiF4 | 四个连续 nibble，已融合 e1 | 每项 1 / 2 / 2 |
| INT8 | M[7:0]、M[15:8] | 每项 1 / 8 / 0 |

class/signaling 先保留槽位，再在同一元素的 A/B 之间判断。`0×Inf` 与 sNaN 产生 invalid；有效 Inf 的符号取 XOR；正负 Inf 同时参与 lane 求和也产生 invalid。不能先将两侧 Inf/Zero 分别 OR，否则会把不同元素误配。只有两侧 class 均为 FINITE 的项参与有限非零指数 MAX；all_negative 继续包含零乘积。

接口与阶段合同：[unpack.md](../../src/spec/dp/lane/unpack.md#11-当前纯-verilog-的紧凑接口)。

参考结构来自 `Quant_LLM_Chip_Codesign/HW/PE/PEGroup/DataUnpack.scala`，读取时仓库 HEAD 为 `5a5037ad03b656ea975ef594d0aca4dc5ef96a39`，文件 SHA-256 为 `abbf827c6c8ad47df773dcfb6033ab4b4468192da34683c4c0fff31598d58e8b`。采用字段分离和配对分类组织；本项目维持 I1F10、Q 的低两个 nibble、group scale 归属及当前流水，不复制参考的不同数值布局。

## 3. 验证结果

| 检查 | 结果 |
| --- | --- |
| 新旧解包/bank 并列比较 | **1,052,198 拍一致**，seed=c0126e64，基线从上述 Git 提交读取 |
| 主路固定向量 | **10747/10747** 与有限位宽 CModel 一致 |
| 主路混合参数/协议 | 六组均 PASS；每组 accepted=528、checked=487、reset_cancelled=41 |
| 主路 S1–S7 断点 | **231654** 全部一致 |
| 与基线整 DP 输出比较 | 11 组固定向量及 6 组 mixed 的 output_sha256 全部相同 |
| E 路固定与定向 | 3×961 固定 + 5288 定向全部一致 |
| E 路参数/协议与断点 | 六组均 PASS；每组 144/137/7，断点 **1106924** 一致 |
| 严格 lint | 主/E 各六组参数通过；无位宽/锁存器/组合环豁免 |
| 快照门禁 | 主/E 均通过统一 rtl_gate，未手改通过状态 |

参数矩阵：K4/27/40、K8/27/40、K16/28/40、K4/28/48、K8/32/64、K16/32/64。复位取消数表示已接收但复位时仍在途的事务，不是数值比较失败。

主路数学参考误差保持基线：BF16 max_ulp=3；FP16/TF32/MXFP8 E5M2=1；其余固定浮点集=0；INT8 逐位比较。CModel 一致性与数学误差分别统计。

定向并列比较覆盖 TF32 全部 524288 个有效编码、FP16/BF16 各65536编码、四种 Q 与 INT8 的全部字节 A/B 配对、三种 E 的全部四位 A/B 与六位 e1/e2 元数据组合，以及20000拍换型/气泡/复位。H/T 的 B 使用固定伪随机序列，另加 0×Inf、不同元素 Inf/Zero、正负 Inf、sNaN/qNaN 和负零定向；这不是全输入组合形式证明。脚本与日志存于主 run 的 compact-equivalence/，大编译产物在收尾释放。

| 证据 | 多精度 | E |
| --- | --- | --- |
| Run ID | `20261106T074807268573Z` | `20261106T074807256233Z` |
| Export ID | `DP_verilog_1822351f0798f2f3` | `DP_verilog_e_bc58d9180cba1ac7` |
| 源指纹 SHA-256 | `1822351f0798f2f32c229087d23d3e6fe4daec2570125c60d2c055f5d03fa0be` | `bc58d9180cba1ac75c622dd6aa6230ad8e06873042aaf34d6d8b18307697bdc0` |
| 验证回执 SHA-256 | `a508711ae539ca27c8d3610eb6ca9216fdb05379f541ea085e56eb65df745c06` | `fb9ccad30daf6235727d0e9441e0eaa166df0ac5491a8a87eca005093e960421` |

命令（Verilator 5.030，GCC toolset 10，CCACHE_DISABLE=1，CXXFLAGS=-std=c++20 -fcoroutines）：

```sh
python3.11 test/run_verilog.py --implementation verilog --phase all
python3.11 test/run_verilog.py --implementation verilog --frontend e --phase all
python3.11 scripts/rtl_gate.py DP_verilog_1822351f0798f2f3
python3.11 scripts/rtl_gate.py DP_verilog_e_bc58d9180cba1ac7
```

本次是普通功能重构验证，未标记重要节点；保留精简摘要及当前回执依赖的输入、输出、断点、日志，释放临时二进制/C++/对象文件。未运行 DC 或功耗，不以接口宽度或功能仿真声称 PPA 收益。

## 4. RTL 自检

| # | 检查项 | 结果与范围 |
| --- | --- | --- |
| 1 | 常数语义 | 通过；新增 atom/紧凑宽度由 DP_UNPACK_* 派生，既有格式编码表保持 |
| 2 | 宏位置 | 通过；仅 dp_defs.vh 定义，带 include guard |
| 3 | 组合 assign | 通过；新解包/配对/选字段均 assign/generate |
| 4 | 条件按位组合 | 通过；先比较或归约成单 bit，再组合 |
| 5 | 数组选择 | 通过；generate 常量索引，格式 MUX 显式 |
| 6 | DFF 保存 | 通过；所有新增 S1 保存复用 dp_lib_DFFE，就地紧凑两行 |
| 7 | 单变量声明 | 通过；端口和变量逐行完整声明，具名连接对齐 |
| 8 | 寄存类型 | 通过；payload 不复位，控制保持同步低有效复位 |
| 9 | 命名 | 通过；r1_*、功能名_d、u_/ff_，没有裸 a/e/f 局部数值 |
| 10 | 数据使能 | 通过；rst_n & in_valid，气泡不改 payload |
| 11 | 目录与清单 | 通过；新模块在 unpack/，只加入主 files.f；不改冻结 SV |
| 12 | localparam | 通过；槽号使用常量推导，无宏纯别名 |
| 13 | 功能名称/注释 | 通过；参数、端口、局部量说明用途与阶段，乘积术语正确 |
| 14 | 打包/解包 | 通过；S1 紧凑保存与输出相邻，不恢复通用 Number |
| 15 | 字段切片 | 通过；布局宏集中，bank 按精度取对应字段 |

以上为本批涉及模块的审查；不表示所有历史代码已经迁移到本批命名。完整语义换行与 DFF 局部格式保护经 Verible 重放检查。
