> 功能：定义新增8/12个QE组的DP装配与后端；范围：T8H16Q96E192/T8H16Q128E256；版本：v1.12；修改时间：2026-11-12 20:18:00 +0800；对应代码：src/verilog/top/dp_top_t8h16q96e192.v、dp_top_t8h16q128e256.v、top/common/dp_top_mixed.v、src/cmodel/lib/config.cpp。

# Q96E192 / Q128E256 扩展合同

用户授权本批方案、CModel、RTL验证和独立DC/功耗。两种结构保持L8/II=1，同周期S6全局移位，S7完整carry-save规约。既有E-only v1.11保持不变。v1.11→v1.12：~~8/12个QE组仅为后续候选~~ → 新增固定包装，复用现有QE组和扩展后端。

| 顶层 | 基础+扩展 | 总组/含C源数 | Q/E原生K | A/B各宽 | scale/e1/e2每侧 | S7 |
| --- | --- | --- | --- | --- | --- | --- |
| t8h16q96e192 | 4个v1.8全精度 + 8个v1.9 QE | 12/13 | 96/192 | 768 | 96/48/24 | S44 |
| t8h16q128e256 | 4个v1.8全精度 + 12个v1.9 QE | 16/17 | 128/256 | 1024 | 128/64/32 | S45 |

## 参与与组输出

Q为四种MXFP8/6，E为MXFP4/NVFP4/HiF4；Q/E激活全部group，T8/H16/INT8 K32只激活基础四组。扩展复用dp_group_qe和dp_lane_qe，不修改其流水。Q在S2求局部指数MAX、S3局部对齐，E绕过Q宽移位并在S4消耗局部e2；两者均在S5输出sign/U31 magnitude/S10 A_raw/S10 compare_exp/special/valid，与基础四组和C同拍。无新增寄存器、无请求内时间复用。

每组占A/B连续64bit、scale8bit、e1四bit、e2两bit。Q每组8元素、MX量化块32，因此逻辑scale编号floor(g/4)；MXFP4为floor(g/2)，NVFP4为g，HiF4为floor(g/4)。Q96/Q128分别3/4个MX32块，E192/E256分别6/8个MX32、12/16个NV16、3/4个HiF64块。物理每组scale字节由输入适配层广播，不改变量化粒度。

## S6 MAX与同周期对齐

participate随请求保存至S5/S6：它决定组是否属于本笔计算；numeric_active=participate且有限非零，只决定数值MAX/移位。非参与组不竞争MAX、数值叶子为零、special归约贡献零、负零AND贡献一，旧payload不能污染T/H/INT8。参与特殊/负零必须独立处理，不能因幅值零而丢弃。

基础四组+C和扩展8/12组各自做带active的signed MAX，再合并成唯一Emax。默认每组U31低补八零、C U32低补七零为U39，各自一次净移位A_raw−Emax、右移RTZ，再恢复符号为S40。全部来源使用同一个Emax，不先分支舍入求和。扩展MAX最深4/5个比较层；实际1GHz可行性由独立DC证明。

## S7与S8

全部13/17个叶子先符号扩展至GLOBAL_W+ceil(log2(N))=44/45。基础四组经4:2后与唯一C经3:2得两行。扩展8组用2+1共3个4:2；扩展12组用3+1+1共5个4:2得两行。另一个4:2合并基础与扩展两行，按本笔Q/E参与标志同时片选两行，最终唯一CPA；T/H/INT8片选基础两行。S8保留完整S44/S45作abs/LZD/RNE，INT32仍取原定点坐标回绕。

默认LOCAL28/GLOBAL40，验证另覆盖27/40、32/64（SUM68/69）。同步低有效rst_n、valid逐拍推进、payload有效更新、原子A/B/C握手与无输出背压不变。C只加一次；本DP没有跨请求累加驻留，D反馈到下一请求C仍受L8 RAW约束。

## 验证和证据

每种profile独立冻结、14campaigns、11格式共10747原生向量；Q96/Q128四格式来自low32/low48各961笔，E192/E256三格式复用同源已导入向量。额外覆盖每个物理组、Q32/NV16/MX32/HiF64边界、正负抵消、特殊和全负零、Q↔E↔高精度切换、失活毒化、气泡和复位、S2–S7断点和CSA行恒等式。

DC为N12 TT/0.7V/85°C、1GHz、ICG、LOCAL28/GLOBAL40、L8/II1，setup/hold/电气/VT全部验收；需要修复则新run保留来源，不放宽最终约束。功耗每profile测BF16 K16、MXFP8 E4M3原生Q K、MXFP4原生E K，同源1024笔Qwen3-8B MLP负载，512ns原生门级SAIF、逐笔RTL/门级和逐引脚活动审计。功能存在不代表时序/功耗通过；结果以独立records为准。
