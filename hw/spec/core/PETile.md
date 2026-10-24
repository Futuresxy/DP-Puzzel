# PETile.scala：full 复用通路

对应源码：[PETile.scala](../../chisel_src/core/PETile.scala)。来源 commit 和源文件 SHA-256 见 [迁移指纹](../full-reuse-source.json)。

## 保留的四层 full 通路

PETile → N 个 MidGroupFull → 每个 4 个 PEGroupFull → 每个 4 个 SubPE。N=1..4 是沿 K 的空间规约，全部 MidGroup 参与每个输出；这不是 M/N 阵列。一个 PETile 只有一个 C/D 通路，每个 AB+C 事务产生一个 FP32 D，没有隐藏的跨事务 accumulator 或 GEMM 调度器。

`dimk=16*N` 为 W16 packed word 数，对应 native K 容量 H=16N、Q=32N、E=64N；三模式共享资源不可相加。`alignWidth=40..64`；groupSize 固定 4。通过唯一 `DesignConfig(midGroups,alignWidth)` 配置，JSON 字段为 mid_groups 和 align_width；每个 MidGroup 固定 H16Q32E64，无 family 裁剪。例见 [配置](../../configs/README.md)。RTL 名 `PETile_H…Q…E…`，非默认对齐加 `_W…`，完整布局保存在 manifest。

## 运行接口与 batch 状态机

| 端口 | 协议与语义 |
| --- | --- |
| in_cfg | Decoupled；idle 时 ready，锁定 A/B data/scale 格式、C 格式、rm、FP32 输出类型 |
| in_ab | Decoupled；A/B packed 数据、scale 和 last |
| in_c | Decoupled；每个 AB 事务对应一个 W32 C carrier |
| out_result | Valid；FP32 result 和原事务 last，接收端必须每拍消费，无 ready |
| out_idle | 完全空闲且可接受下一 batch cfg |

`Idle -> Accepting -> Draining -> Idle`。cfg fire 后下拍允许数据；AB/C 只有同时 valid 才会一起 fire，单边到达不消费，输入 producer 应独立拉高 valid 并保持 payload 到握手。每次原子接收生成一个 D；last 随有效 AB 接收后进入 Draining，禁止新数据和新 cfg，直到最后一个输出才回 Idle。batch 必须发送 last，否则不能配置下一 batch。连续事务 II=1，气泡逐拍前进；一旦接收，内部不可停顿。复位丢弃在途事务，状态/valid 同步清零，数据寄存器不复位；外部应在复位后重新发 cfg。

A/B payload 的 data_type 与 sf_type 必须匹配 batch cfg，并有断言；重复字段此次保留以方便源代码审查，后续再决定是否删减。合法模式和数据打包见 [Interfaces](Interfaces.md)、[FormatCompat](../config/FormatCompat.md)。C type 0/1/2 为 FP32/FP16/BF16（后两者放低 16 位），rm 0..4 为 RNE/RTZ/RDN/RUP/RMM；out_type 仅 FP32=0。非法 cfg 在握手时断言，并保持 Idle，不能默认为另一模式。

## 公共 C/D 路径与位宽

原始 C 延迟 9 拍，然后 CUnpacker 两拍解码/无损规格化，与所有 MidGroup 在 S11 对齐。每个 MidGroup 输出 magnitude W(A+1)+sign、anchor W11；C 为 magnitude W24+sign，默认 C 坐标 F23。C 补 `A+2−25` 个低零进入公共 W(A+2) 窗口（默认 W42/F40）。零项屏蔽 anchor，特殊值 sideband 独立合并。

S12 注册各项 magnitude/sign、MAX index 和饱和 shift；S13 对 N 个 MidGroup+C 共 N+1 项按逻辑 magnitude 右移再施符号，实现 signed RTZ。MAX 旁路，其他 N 项移位。S14 平衡树求和：`Wsum=A+2+ceil(log2(N+1))`，默认 N=1/2/3/4 分别 W43/44/44/45，anchor 同时加增长位数，避免二进制小数点漂移。允许 N=3，非二次幂结构必须检查。

S15 abs/LZD，S16 规格化并提取 W26（hidden+23 fraction+round+sticky）；S17 舍入，S18 FP32 打包。特殊值优先级 NaN（含 +Inf 与 −Inf 叠加）> 单符号 Inf > zero > 有限值。RoundIncrement 为本地组合模块，替代原 FuDian 依赖，需独立 RTL 验收。NVFP4 这里只施加 block scale，不包括额外张量级 scale；HiF4 保留源实验编码，外部标准尚未确定。

## 周期合同与待验收

S00 是接收前输入 offer；其有效内容依次经过 18 个寄存边界，在 S18 输出。若仿真把接收上升沿编号为 0，结果在编号 17 的上升沿后可见，scoreboard 必须统一 offer/edge 口径。II=1 仅针对同一 batch 的连续接收；配置和 batch drain 开销另计。

| 阶段 | 边界 |
| --- | --- |
| S01 | PG 解包与 C raw 延迟开始 |
| S02–S04 | SubPE products、anchor、对齐/局部和 |
| S05–S07 | PG align、sum、scale；anchor S06 / data S07 |
| S08–S11 | MidGroup align、sum、精确规格化；C 在 S10/S11 解码 |
| S12–S14 | MidGroup+C 公共 MAX、align、sum |
| S15–S18 | 最终 LZD/sticky、舍入/FP32 输出 |

当前只完成源码审查支持、编译/展开及导出结构检查，不存在本分支 RTL bit-exact 或误差界验收。待补独立 golden 与 SV testbench：全格式/scale、舍入 ties 与进位、subnormal/overflow、特殊值、严重抵消、AB/C 单边等待、连续/气泡、last/drain、复位、非法配置、N=1/3/4 和窗口边界。未通过同份 RTL 验收前不进入 DC/power。
