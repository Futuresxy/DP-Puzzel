# 六种 DP 的真实负载功耗实施方案

2026-11-08；本轮已完成数据导入、数学/CModel参考、固定测量计划和执行器；首批15点已完成，验收及数值见 [power_qwen8b_six_1108](records/power_qwen8b_six_1108.md)。本方案对应单 DP，不包含阵列、存储或整个 Qwen 模型的功耗。

## 1. 已准备的输入

数据位于 `test/data/power/<format>/K<logical_k>/qwen3_8b_mlp_down_proj_1024/`，来源是 Qwen3-8B 第0层真实 MLP down_proj 的同一组1024个 token/channel/k_start 样本。保留上游量化编码、scale 和 HiF4 元数据，按原生 K 提取，不重新量化、不补造样本、不跨样本拼接。

| 格式 | 已准备逻辑 K | 每 K 笔数 |
| --- | --- | ---: |
| BF16、FP16 | 16 | 1024 |
| MXFP8 E4M3、E5M2 | 32、64 | 1024 |
| MXFP4 E2M1、NVFP4、HiF4 | 64、96、128 | 1024 |

15套、15360笔独立格式/K输入。数据跨格式共用来源样本和C；同一格式的较小K数据是较大K数据的位精确前缀，已检查数据、scale及HiF4元数据。C是同一BF16参考GEMM在k_start之前的FP32前缀累加值，每笔独立使用一次；不是本次D回接下一笔C，不代表低精度长K累加链。

数学golden是独立Fraction精确解码、求和后一次FP32 RNE；CModel golden使用28/40窗口及各适配前端。当前15360笔数学结果全部匹配来源FP64 golden的FP32编码；六架构36864次CModel计算与数学结果全部一致、max ULP=0。它不代替RTL/门级验证。

入口：[数据说明](../../test/data/README.md#qwen3-8b-mlp-功耗数据)、[验证摘要](../../test/results/qwen3-8b-power-data.md)、[固定计划](plans/qwen3_8b_first3.json)。

## 2. 首批测量矩阵

先打通dp_top的三种格式，再对其余兼容架构重放，总计15个点；不对不支持的格式报告零功耗。

| 顶层 | BF16 K | MXFP8 E4M3 K | MXFP4 E2M1 K |
| --- | ---: | ---: | ---: |
| dp_top | 16 | 32 | 64 |
| dp_top_t8h16q32e96 | 16 | 32 | 96 |
| dp_top_t8h16q32e128 | 16 | 32 | 128 |
| dp_top_t8h16q64e128_opt | 16 | 64 | 128 |
| dp_top_e64 | 不支持 | 不支持 | 64 |
| dp_top_q32e64 | 不支持 | 32 | 64 |

每点显式绑定catalog中的run、export、原始回执、DDC/SDC/网表及校验和。E64/Q32E64对应CModel前端e/qe。后续FP16/E5M2/NVFP4/HiF4沿用已准备的数据，每种格式另生成活动文件。

当前可执行的计划检查命令只读验证数据/产物身份并写计划，不运行EDA、不产生门禁PASS：

```bash
python3.11 hw/power/scripts/prepare_qwen_plan.py \
  --output hw/power/plans/qwen3_8b_first3.json
```

计划固定了当时选择的run；执行器必须消费该计划，禁止执行时再次按目录时间挑选网表。

## 3. 程序组织与接入顺序

已实现入口及职责：

```text
hw/power/
  scripts/
    prepare_qwen_plan.py       # 固定数据和综合网表选择
    setup_dependency.py       # 从固定commit提取4个MIT审计/解析文件
    run_power.py               # 端口激励、RTL/GLS、原生SAIF、PC与逐引脚审计
    report_power.py            # 完整批次hash检查和Markdown/JSON/CSV汇总
  tb/dp_power_tb.sv.in         # RTL与门级共用的固定top计分板模板
  tcl/power.tcl               # 原DDC+DB+SAIF，不重新compile
  configs/machine.local.json  # 本机工具/单元模型绑定，忽略提交
  plans/qwen3_8b_first3.json   # 固定首批15点，计划本身不表示测量通过
  tests/                     # 回执篡改、短回放、X/Z、时长和单位的拒绝测试
  runs/<run-id>/              # 原始活动、日志、报告，仅本地
  records/                   # 验收通过的精简功耗结果
```

命令和本机配置字段见 [README](README.md)。统一入口 `scripts/rtl_gate.verify_power_input` 调用 `scripts/dp_power_gate.py`，显式限定为 archived_dc_reuse_only。RTL重放使用Icarus Verilog；门级使用VCS，同一TB核对D/类型/last及周期协议。审计模块来自固定MIT依赖 [清单](../../dependencies/petile-power.json)。

阶段一：核验输入和环境。验证原DC最终结果、冻结RTL目录指纹和历史回执；确认VCS/Power Compiler许可证、匹配发行版的N12 base/LVT单元模型以及所有实际映射单元/引脚。机器路径与许可证配置只留本地。保持原TT0.7V85°C、1GHz、时钟门控、IO负载和约束，不为功耗重新综合或改动数据通路。

现有RTL门禁包含当前源码/测试新鲜度检查，目录迁移或源码变化可能使历史快照无法直接通过。统一门禁已接入显式冻结版本重放：使用原始files.f/src、核验已有指纹，并由新RTL仿真生产绑定该快照和本次负载的新回执。不得把源树差异忽略后手改manifest。若冻结输入的数值/周期证据无法建立，该点停止。E96/E128的QE可选分支差异不要求仅为本次旧网表测量重新综合，但也不能自动宣称当前源树与它形式等价。

阶段二：准备端口激励与计分板。复用test数据schema和数学操作数布局，logical K不是K_FP16。混合顶层扩展端口按物理宽度高补零，scale按已有基本group槽位装配，C只接入一次。对unsupported数据类型不发射。计分板读取expected.jsonl中与该网表前端匹配的cmodel_results字段，逐笔要求D、datatype、last位精确一致，并核对接受数、输出数和L8/II=1；精确数学参考另作误差统计，不能用ULP容差放过RTL/网表不一致。

阶段三：冻结RTL重放后执行VCS门级重放。同一端口序列先在原快照上验证，再在原映射网表上运行。同步低有效rst_n只复位控制；对各已实现精度bank及扩展组发送合法初始化事务，让无复位数据寄存器进入已知状态。初始化不计为1024个源样本，不使用force内部寄存器。首批只测三格式不意味着只初始化三个模式；无法消除真实功耗引脚X/Z时保留诊断并停止。

阶段四：采集原生SAIF。只在门级运行启用VCS gate-level monitoring和toggle scope，监测整个DUT及ICG/寄存器叶单元；禁止用VCD转换或RTL SAIF代替本轮门级活动。参考现有PETile流程的`+vcs+saif_libcell`、`$set_gate_level_monitoring`、`$set_toggle_region`、`$toggle_start/stop/report`，实际调用形式和选项在本机VCS中验收。使用匹配模型的零延迟门级仿真，记录实际timescale、工具版本和命令。

阶段五：Power Compiler。读取同一次综合的DDC及DB，保留原SDC约束；清除旧活动后read_saif到准确的DUT层次。检查Nets/Ports/Pins显式注释100%，默认/传播补齐为0；VCS省略的真实叶引脚只能由同一电气网络或明确常量补齐，保留网表连接和alias证据。逐叶引脚核对T1/DURATION、TC/时间，检查TX=TZ=0。保留门控时钟的实测零翻转，不将其覆盖为理想时钟活动。

时钟转换时间沿用所选DC约束，核验clock源、ICG输入输出及DFF时钟脚；不能把时钟slew设置误施加到数据、使能或测试脚。报告Internal/Switching/Leakage/Total、层次功耗、注释覆盖和实际引脚活动。源码实现可参考外部项目的native_power.py、saif_activity.py、netlist_activity.py；先核对依赖/许可证并做DP接口适配，不复制其整个源码树，也不依赖硬编码的外部项目路径。

## 4. 固定活动窗口

每个测量点重置后完成初始化，再按源顺序发射全部1024笔，每笔一次，II=1：

```text
初始化（单独计数）
事务0..255       预热，SAIF关闭
事务256..767     稳态测量，共512周期
事务768..1023    继续发射，SAIF关闭
排空流水         检查全部1024笔输出
```

开始/结束使用同一时钟相位，在驱动事务256/768之前调用toggle控制，避免TB竞争；时间间隔必须恰好512个完整周期，即1GHz下512ns。测量边界按输入发射时间定义，包含该时间段内不同流水级的在途事务，不能把输入ID区间误当成只统计这些ID的全部生命周期。测量窗内保持rst_n=1、valid连续、目标精度固定。

## 5. 结果和失败判定

每个run保存plan、输入/期望、冻结RTL重放回执、门级输出、VCS日志、窗口起止、原生SAIF、必要alias补齐及映射、Power Compiler Tcl/日志/报告和审计结果。只有全部检查通过才写records中的实测数字；计划中的power_mw保持null；完成数据只写测量记录，避免将计划误用为验收。

报告整DP的平均mW，同时计算`pJ/MAC = Total_W / (logical_K × frequency_Hz) × 1e12`，C加数不另计MAC。K不同的架构必须同时给出功耗和能效；不能把整DP功耗直接解释为单MAC成本。若列OP按2 OP/MAC说明。窗口能量为Total_W×512ns。

这些结果是综合后、零延迟真实活动驱动、CTS/布线前的平均功耗；无SDF/SPEF导致不能代表布线寄生或真实毛刺功耗，也不是芯片整机功耗。失败点不填0，不与完成点混为一列。普通运行按统一保留规则处理，具体重要run及长期保留理由在结果形成后与用户确认。
