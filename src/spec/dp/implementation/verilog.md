> 功能：定义手写 RTL 实现映射及验证合同；范围：多精度/E-only 单 DP、冻结的 SystemVerilog 历史参考、L8、源码快照；版本：v1.6.2；修改时间：2026-11-06 13:54:29 +08:00；对应代码：[dp_top.v](../../../verilog/top/dp_top.v)、[dp_top_e.v](../../../verilog/top/dp_top_e.v)、[dp_tb.v](../../../../test/rtl_tb/dp_tb.v)。

# 单 DP 手写 RTL 实现合同

本页记录 v1.6.2 手写 RTL，S5 采用 [scale 合同](../group/scale.md) 的 14×8 无符号乘法及符号旁带。主要交付采用 IEEE 1364-2005 Verilog；按用户最新要求将 SystemVerilog 冻结为 T8H16Q32E64 历史参考，来源见 [SV 冻结说明](../../../verilog/systemverilog/README.md)。后续新功能与 E 专用设计只维护现用 CModel/Verilog，不要求 SV 同步。仅实现一个 DP，未进入计算阵列。

## 1. 文件组织与实现边界

模块名和文件名统一为 `dp_<function>.v`；一文件一 module，常量及纯函数在 `.vh`。SystemVerilog 对应模块位于独立 `systemverilog/`，不能混编两个同名 module。详细文件清单分别由 `src/verilog/files.f` 和 `src/verilog/systemverilog/files.f` 固定，禁止 wildcard 混入测试或另一实现。

| 功能 / 阶段 | Verilog 文件 | 寄存归属 |
| --- | --- | --- |
| 顶层 DP、请求控制、C transport | [dp_top.v](../../../verilog/top/dp_top.v) | valid/last/type S1–S8、C raw S1–S4、C S5、S6/S7/S8 |
| T2H4Q8E16 基本组 | [dp_group.v](../../../verilog/group/dp_group.v) | scale S1–S4；组 token S5 |
| T1H2Q4E8 lane | [dp_lane.v](../../../verilog/lane/dp_lane.v) | S1 子模块有效控制、乘积 S2、叶 S3、SOP S4 |
| 固定 layout 解包/寄存 | [dp_lane_unpack.v](../../../verilog/unpack/dp_lane_unpack.v) | S1 两份 E10/M16/S4；class/signaling 旁带，扩展元素视图只是连线 |
| A/B 元素解码 | [dp_operand_unpack.v](../../../verilog/unpack/dp_operand_unpack.v) | 组合；S1 由 dp_lane_unpack 注册 |
| scale / C 解包 | [dp_scale_unpack.v](../../../verilog/unpack/dp_scale_unpack.v)、[dp_c_unpack.v](../../../verilog/unpack/dp_c_unpack.v) | 组合；分别由 group/top 注册 |
| 尾数共享 bank | [dp_mantissa_bank.v](../../../verilog/lane/dp_mantissa_bank.v) | 组合；输入 mux/隔离与重构属于 bank |
| 乘法叶 | [dp_mul_unsigned.v](../../../verilog/arithmetic/dp_mul_unsigned.v) | 组合；HH/HL/LH/LL 和 scale-pair 分实例 |
| 指数共享 bank / 加法叶 | [dp_exponent_bank.v](../../../verilog/lane/dp_exponent_bank.v)、[dp_exponent_add.v](../../../verilog/arithmetic/dp_exponent_add.v) | 组合；两套宽/窄加法器，E 共用一份 e2 和 |
| MAX | [dp_max_tree.v](../../../verilog/arithmetic/dp_max_tree.v) | 组合；lane/group/global 分别实例化 |
| S3 完整局部对齐 | [dp_lane_align.v](../../../verilog/lane/dp_lane_align.v) | E pair、模式落位、四路 RTZ、符号恢复；S3 DFF 由 lane 持有 |
| E lane 坐标左移 | [dp_lane_e_shift.v](../../../verilog/lane/dp_lane_e_shift.v) | S3 和先扩展再左移；组和由 group 的 S4 DFF 捕获 |
| 局部幅值右移 | [dp_rtz_shift.v](../../../verilog/arithmetic/dp_rtz_shift.v) | 组合；每 lane 四路 |
| SOP 规约 | [dp_sum_tree.v](../../../verilog/arithmetic/dp_sum_tree.v) | 组合；lane/group/top 三个层级分别注册 |
| scale 注入 | [dp_scale_multiply.v](../../../verilog/arithmetic/dp_scale_multiply.v) | 组合；公共 14×8 无符号，输出 22 位幅值 |
| LZD | [dp_lzd.v](../../../verilog/arithmetic/dp_lzd.v) | 组合；S5 group/C、S8 output 独立实例 |
| 全局对齐 | [dp_global_align.v](../../../verilog/top/dp_global_align.v) | 组合；MAX、net、符号恢复归入本模块 |
| 双向幅值移位 | [dp_bidir_shift.v](../../../verilog/arithmetic/dp_bidir_shift.v) | 组合；方向 bit reversal + 一个右移核心 |
| FP32 输出 | [dp_fp32_round.v](../../../verilog/arithmetic/dp_fp32_round.v) | 组合；S8 结果由 top 注册 |

各路径命名可用于层级统计。多精度 S3 的 E pair/符号恢复归入 dp_lane_align，E 的 S2 pair 复用 N=2 的 dp_sum_tree；组 abs、特殊摘要与 transport 寄存器仍属于直接拥有它们的 lane/group/top；不能把它们在父子统计中重复计数。没有为了统计添加 `dont_touch`、时钟域或额外寄存级。v1.5 旧快照的 28/40 同工况面积/时序见 [E64 DC 对比](../../../../hw/dc_syn/records/e64_n12_comparison_20261105.md)，v1.6 新快照尚未重跑 DC/功耗，旧结果不授予新 RTL。

S1 每侧实际复用两份 E10/M16/S4 寄存器，按 T/H/Q/E/INT8 打包和展开；没有为各格式单独保存一套宽尾数。分类旁带独立，TF32 只启用第一个 atom。M/E/S 布局也纳入 CModel 断点比对。

## 2. 参数与数值坐标

构建参数为 `K_FP16`、`LOCAL_W`、`GLOBAL_W`。分别对应 CModel 的 `k_fp16`、`local_shift_mag_width`、`global_signed_align_width`。现用 Verilog 只开放 L8；L9 仍是 CModel 探索选项。默认 K16/28/40。LOCAL_W 与 GLOBAL_W 可独立调整，要求 LOCAL_W≥27、GLOBAL_W≥max(LOCAL_W+4,33)。中间模块从父层参数派生树宽、补零、LZD/指数控制及各模式 SxIxFx，DSE 直接修改窗口参数。

| 派生量 | 公式 |
| --- | --- |
| 基本组数 | `G=K_FP16/GROUP_H`，`GROUP_H=4` |
| 局部 TC 叶宽 | `LOCAL_W+1` |
| lane SOP | `LOCAL_W+1+ceil(log2(Q_LANES))` |
| group SOP | `lane_width+ceil(log2(LANES))` |
| S5 幅值 | `group_width−1`，符号独立 |
| 全局幅值 / 浮点 F | `GLOBAL_W−1` / `GLOBAL_W−2` |
| 最终 SOP | `GLOBAL_W+ceil(log2(G+1))` |
| LZD 计数 | `ceil(log2(magnitude_width+1))` |
| anchor | 根据可表示的最小实际指数/最大 raw anchor 推导最小有符号宽度；默认 10 |

自然树支持单项和非二次幂项数，奇数叶在下一层显式符号扩展。默认最终扇入 5，K4/K8 分别为 2/3；宽度不会因向上取整的树形组织丢失进位。

S5 仍为 `value=(-1)^sign × magnitude × 2^(A_raw-(M-1))`。不同格式 F 在 `A_raw=alpha−F+(M−1)` 中吸收；S6 不能再次扣 F。`e=A_raw−z` 只用于比较，原幅值先静态低补零，再按 `A_raw−E_max` 做一次双向移位。详见 [逐级格式](../common/stage-formats.md)。

格式字段、bias、枚举和 FP4 编码表属于固定数值合同，不能把任意改编码包装成普通窗口扫参。位宽下界、K 和派生关系在仿真构建中检查；不合法配置不得用于导出或 PPA。

## 3. 控制、复位与低活动

采用同步低有效 `rst_n`，全局同拍作用于所有流水有效位，清除 last/type 控制并取消在途结果。数据通路无需复位到零；只有有效请求进入本级时才更新数据寄存器。复位沿上的旧输出不能被下游作为有效事务消费。

v1.5 → v1.6：~~同步高有效 reset、功能模块内直接保存流水寄存器~~ → 同步低有效 `rst_n`、显式参数化 DFF。外部需把复位事件取反后接入；数值、L8/II=1、容量及默认 28/40 不变。冻结 SV 保留旧接口。

流水存储的生产单一来源为 `src/verilog/common/`：`dp_lib_DFFRU` 每拍推进并同步清零 valid/last，`dp_lib_DFFRE` 保存需复位且有使能的控制；`dp_lib_DFFE` 无复位，仅在 `rst_n & source_valid` 更新 payload。`ff_sN_sM_<field>` 表明时钟边界；实际顺序逻辑只位于 `dp_dff_en.v` 和 `dp_dff_sync_reset.v`。元数据与数据使用同一使能，不产生新增延迟或级间 ready。

功能组合层使用 assign/generate；译码、符号分离、特殊值归约、舍入的中间量具名，保持原有有限位宽和两次 RTZ。参数/端口/变量逐项声明，普通实例使用 `u_`，循环采用角色名。规范见 [RTL style](../../../../.skill/dp-rtl-code-style/SKILL.md) 与 [命名](../../../../.skill/dp-naming-convention/SKILL.md)。DC 优先从 DFF 实例名识别阶段，同时保留历史命名解析；没有新增 false path 或 dont_touch。

三路原子 ready、逐请求 type、无输出背压和 last 透传完全遵循 [接口](../dptop/interface.md)。缺失输入只产生 bubble，不冻结已接受请求。非法 datatype 元组不握手；合法 NaN/Inf 必须按正常 L8 输出。

S2 bank 对未使用乘法器输入清零；T 只使用一套，BF16、Q、INT 按路由隔离其余单元。S5 scale 单元仅在 NVFP4/HiF4 模式使能。幅值乘法与旁路共享组和 abs，符号与幅值同拍注册。INT8 在 S6 旁路指数移位，并在 S8 旁路浮点舍入；所有格式仍为 L8。

## 4. 验证、导出与范围

[纯 Verilog TB](../../../../test/rtl_tb/dp_tb.v) 直接读取 `DP_INPUTS_V1`。默认仅对现用纯 Verilog 做 Verilator 编译/仿真，以 Icarus 单独检查严格 Verilog 语法及四态行为。SV/双版选项保留历史重放用途，冻结 SV 不参与新版本必需门禁。验证必须区分：对 CModel 位精确一致、相对独立数学参考的精度、RTL 时序/PPA；本轮仅前两类已有模型/仿真证据。

验证前冻结源到 `hw/rtl/DP_<implementation>_<fingerprint>/`，每个源文件标识 `RTL_ID`。清单记录源码及快照 SHA、顶层、格式常量、参数化状态和验证范围。实际参数、工具、测试输入/输出及断点计数记录在回归摘要；快照仅在对应检查通过后标为 passed；完整回归经新版后端门禁复核后才生成验证回执并设置 `ppa_eligible=true`，部分/失败回归仍为 false。此快照是参数化源码，不冒充完成综合的特化网表。

Verilog 的 `lane_fraction` 使用 datatype 对常量进行选择，避免对运行时 `elements(t)` 调用 DC 不接受的 `$clog2`；各编码的 F 值与原公式相同，未改变截断或流水。

`python3 test/run_verilog.py --implementation verilog --phase all --local-w 29 --global-w 33` 可验证自选窗口。K16 固定向量使用同配置 CModel 重新生成有限位宽期望，数学参考仍来自同一批向量的精确结果。混合回归另外覆盖 K4/K8/K16 的树深和流水断点。

测试配置和笔数见 [RTL 验证报告](../../../../test/results/verilog-v1.4.md)。N12 TT DC 结果对应历史 27/40 配置，见 [时序分析](../../../../hw/dc_syn/records/dp_n12_timing_20261105.md)。

## 5. 修订记录

| 版本 | 时间（+08:00） | 修改 |
| --- | --- | --- |
| v1.4.2 | 2026-11-04 23:05:38 | 新增单 DP Verilog 实现和 SystemVerilog 对照映射，落实同步复位与 L8；增加标准 Verilog TB、快照和 Verilator 验证。数值合同不变。 |

## 6. 分类型模块与组合配置建议

当前已新增 unpack/dp_lane_unpack_e.v、lane/dp_lane_e.v、group/dp_group_e.v、top/dp_top_e.v 和 files_e.f，保留原多精度路径。下面更完整的子目录布局及 dp_backend.v 仍为后续目标，尚未实施；共用算术模块只保留一份：

~~~text
src/verilog/
├── arithmetic/               # 共用固定功能算术库，沿用现有目录
├── unpack/                   # 共用解码；必要的专用解码另有唯一模块名
├── parameter/                # 共用格式常量与数值函数
├── lane/
│   ├── multi/                # 现有多精度 lane 及其专属 bank
│   └── e/                    # E lane、pair 与局部 e2 融合
├── group/
│   ├── multi/                # 多精度 group
│   └── e/                    # E group
├── top/
│   ├── dp_backend.v          # 拟抽出的公共 S6–S8 寄存及计算
│   ├── dp_top.v              # 保持现有多精度对外入口
│   └── dp_top_e.v            # E-only 薄装配入口；混合入口按需增加
├── filelists/                # 每种组合有明确 top 和源清单
└── systemverilog/            # 已冻结的历史参考
~~~

模块定义全局唯一，例如 E 新模块用 dp_lane_e/dp_group_e；现有多精度模块可保留 dp_lane/dp_group 名称。目录区分不允许两个同名 module 混编。算术库按参数实例化，例如两个前端共用 dp_sum_tree 的源码，但项数/位宽、实例和寄存归属分别明确。专用 E 解包不依赖整个多精度大模块保留所有格式通路；固定功能的格式解码、scale 和后端算术适合共用。

src/configs/dp/e64.json 已用于 CModel 的兼容参数+frontend 选择；RTL 尚未接入。以下 groups 列表仅示意未来的通用组合 schema，当前 CModel/RTL 命令均不支持：

~~~json
{
  "profile_id": "mixed_t4h8q16e64",
  "groups": [
    {"kind": "multi", "count": 2},
    {"kind": "e", "count": 2}
  ],
  "local_w": 28,
  "global_w": 40
}
~~~

构建入口据此选择模块、顶层、静态参数和文件清单，CModel/测试读取同一 profile。datatype 仍逐笔输入，不通过运行时选择两套完整 DP 来实现 profile。前端模块数量与类型在 elaboration 时确定，未实例化的计算通路不进入该设计。

公共后端当前尚未完整抽取：dp_global_align/dp_sum_tree/dp_fp32_round 已是组合模块，但 S6–S8 寄存器和相关控制仍在 dp_top 中。拟抽取的 dp_backend 必须同时承接这些寄存器、valid/last、特殊值与零符号规约；C 的 S1–S5 路径只保留一份。组边界仍保持原 S5 layout，经静态补零适配送入后端，不暗增周期。

本批 E 路径复用已有算术模块，S6–S8 寄存器继续由各自 top 持有；没有为实现 E64 先重构原 dp_top。两种前端分别验证，原多精度回归保持原结果/周期。未来通用后端寄存模块或混合组迁移仍须独立回归，不能把 CModel 的函数抽取当作 RTL 已完成相同重构。

各 profile 的 export ID、源指纹、参数、CModel 指纹与验证回执分别保存。共享模块修改后重验依赖它的活动 profile；SV 历史参考不加入同步维护。按实际实例统计 PPA，不能把源码复用当成跨并发流水级的物理算术复用。

## 7. E-only 实现与验收

顶层 [dp_top_e.v](../../../verilog/top/dp_top_e.v)，显式清单 [files_e.f](../../../verilog/files_e.f) 只编译显式列出的纯 Verilog 源，不含多精度 lane/group/top 或历史 SV。默认 E64=4×E16=8×E8；参数及外部请求接口沿用 K_FP16/LOCAL_W/GLOBAL_W，K_FP16 在此仅为兼容容量索引，4/8/16 对应 E16/E32/E64。只接受 MXFP4/NVFP4/HiF4 及其合法 scale、FP32 C；其他元组拒收且不阻塞在途输出。

| 模块 | 计算/寄存边界 |
| --- | --- |
| [dp_lane_unpack_e](../../../verilog/unpack/dp_lane_unpack_e.v) | 每 lane 的 A/B 各一份组合解码，输出8×4位幅值和8位符号；不持有寄存器 |
| [dp_lane_e](../../../verilog/lane/dp_lane_e.v) | 实例化 E 解包并持有 S1 幅值/符号寄存器，S2 8 个 4×4 和四个 signed10 pair，S3 两层树到 signed12；末端 S4 组合小左移至 signed14 |
| [dp_group_e](../../../verilog/group/dp_group_e.v) | S1 scale 解包、S2 系数预乘、S3 anchor 准备、S4 两 lane 组和/abs 至幅值14+sign、S5 14×8 scale 或 MX 旁路/LZD/token |
| dp_top_e | 一份 C raw S1–S4、C S5；共用 dp_c_unpack/dp_global_align/dp_sum_tree/dp_fp32_round，S6/S7/S8 寄存与 valid/last 由自身持有；没有 INT32 数据路径 |

E 前端无元素指数 MAX/差值/右移对齐；HiF4 e2 已融入 lane coefficient。MX/NV 两个低零是静态连线，S6 组间及 C 的全局移位保持 GLOBAL_W=40。输出 S5 保持 M=LOCAL_W+3 的字段宽度及到达拍。HiF4 的 F/anchor/z 使用 [专用坐标](../group/dp_group_E.md)，不能套用原多精度 HiF4 的字段原值。

`python3 test/run_verilog.py --frontend e --phase all` 使用相同 DP_INPUTS_V1 读取、原子 ready/预沿 L8 scoreboard、独立调度队列和数学精度统计；`DP_E_FRONTEND` 只选择 TB 的 DUT 与观察适配，不作为设计宏。S1–S7 的 E 观察点见 [dp_tb_e_trace.vh](../../../../test/rtl_tb/dp_tb_e_trace.vh)。每次验证创建 `DP_verilog_e_<fingerprint>`，由门禁完整检查 3×961、5288 定向与六组参数，成功后真实生成回执。多精度 snapshot 的通过状态不授予 E snapshot。

完整结果、来源、配置及长期保留声明见 [E64 验证报告](../../../../test/results/e64-v1.5.8.md)。时序/面积使用独立 DC 报告；没有真实负载功耗或布线后结论。

E 解包模块化修订 v1.5.9 保持 S1–S8 边界和数值语义；新指纹已通过完整 E Verilator 回归（三格式各961笔、5288定向、六组参数及1106924个断点）。既有 DC 报告对应原冻结快照，结构修订不自动继承其 PPA 结论。
