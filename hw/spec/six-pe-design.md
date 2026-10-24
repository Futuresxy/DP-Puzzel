# 五族六种基础 PE：设计与参数合同

本轮在当前修复分支实现用户指定的五族目录、六个合法profile。原MidGroup重命名为PE，下面保留实际PEGroup/SubPE模块；上层提供单输出K_PE、MN_PE，不写阵列代码。原工程只读，固定commit和文件hash见 [six-pe-source.json](six-pe-source.json)。

| profile | 每个PE的PG数 | H/Q/E native K | 计算组织 |
| --- | --- | --- | --- |
| PE_HQE_g4 | 4 | 16/32/64 | 保留全格式部分乘法与分级RTZ复用 |
| PE_QE_g4 | 4 | 0/32/64 | 保留Q/E小乘法和分级RTZ复用 |
| PE_H_g4 | 4 | 16/0/0 | 16个高精度产品一次全局对齐 |
| PE_Q_g4 | 4 | 0/32/0 | 32个FP8/6产品一次全局对齐 |
| PE_E_g4 | 4 | 0/0/64 | 保留窄FP4路径与分级规约 |
| PE_E_g2 | 2 | 0/0/32 | 同一E源码的两组特化，末尾精确补零 |

目录 `pe/PE_H/PE_Q/PE_E/PE_HQE/PE_QE` 各有独立SubPE、PEGroup、DataUnpack、PE文件，类名按用户指定使用下划线。Scala package为dp.pe.h/q/e/hqe/qe；公共接口/算术/连接放Utils，package为dp.utils。每个具体Module独立同名Scala文件，每个Scala有同路径spec。

## H/Q 全局路径与原复用路径的边界

HQE、QE、E保留原数值流程和资源组织，参数传递及代码风格适配不改变其计算拓扑。H/Q的四个PG只做解包/产品组织，删除字内/PG MAX与局部和。H单个11×11得到UQ2.20 W22产品；Q每word两个4×4得到UQ2.6 W8产品，高lane仍为nibble2/sign1，FP6按每byte低6bit存储。

Q只使用E8M0块scale。32元素的共同scale指数在PE层计算一次，在全局MAX之后附加；不需要scale尾数乘法。E4M3/E5M2等**元素**尾数乘法仍然需要。专用解包文件只保留所属格式，H硬连unit scale，Q仅实现E8M0 scale分类/指数。

H/Q流水：S01解包，S02产品，S03平衡MAX，S04指数差，S05独立lane RTZ移位，S06–S09流水加法树，S10/S11规范化。所有加法+&自然增长，H全局和W=A+4、Q为A+5。之后magnitude明确RTZ掉2/3个最低位，输出W=A+2、F=A。没有为了统一结果宽而截断自然和的高位。

HQE/QE/E仍在S07提供PG数据、S08对齐、S09和、S10/S11规范化。六种PE的输入到输出统一11个寄存边界、II1、Valid-only；K/MN的公共C/D保持总18级。cfg在batch排空前保持稳定，内部数据寄存器有效更新且不复位，控制/valid同步复位。

## 输出坐标与 g2/g4

统一原子输出 `{magnitude, negative, top_anchor, is_zero, special}`。对F=pe_align_width：

`value = (-1)^negative * magnitude * 2^(top_anchor-F)`。

默认总W42=S1/I1/F40，magnitude W41。g2内部自然和W41，规格化magnitude W40/F39；最后Cat一个低位0到W41/F40，normalized anchor/sign保持不变。`M*2^(A-39)=(2M)*2^(A-40)`，没有精度丢失。所有E子格式，包括MXFP4/NVFP4/源HiF4均采用这一公共输出坐标。内部raw anchor的增长仍按实际g2/g4分别+1/+2。

统一输出保留位数和周期是公平比较的接口条件；H/Q一次全局RTZ与HQE/QE多级RTZ的损失位置不同，不能据此宣称bit-exact或同等误差。后续数值回归需独立参考，分别记录误差；PPA使用同工艺/PVT/约束和频率，若时序不达标不能直接比较相同频率收益。

## 参数配置

集中入口 [Parameters.scala](../chisel_src/config/Parameters.scala)，详细范围见 [参数spec](config/Parameters.md)。四个可调量默认q_align_width28、group_guard_bits2、pe_align_width40、top_align_width40；窗口只在当前工程附近变化，require在构造时拒绝范围外组合。乘法和加法按自然位宽增长，不开放任意乘/加输出位宽。

这是**Chisel生成时参数**：Parameters默认<JSON<CLI，最终有效值进入manifest。改变参数要重新生成RTL，导出SV已经特化，不把它包装成可随意再次override的SV parameter。每个模块显式收到同一AlignmentConfig，不从sys.env选择电路。

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate config configs/pe_e_g2.json --pe-align-width 44 --top-align-width 44
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/k_1_2_6.json "width scan" --q-align-width 30 --group-guard-bits 4 --pe-align-width 48 --top-align-width 48
```

Q字内窗口与PG guard仅作用于仍采用这些局部阶段的共享/E路径。专用H/Q只用PE全局窗口；K/MN的PE+C窗口可以独立加宽，必须≥PE窗口，较窄输入在边界精确补零。窗口改变可能改变数值误差，不能只靠导出成功判定质量不变。

## K/MN 编排

K_PE按有序profile列表沿K规约，共享一个C与FP32 D处理；MN_PE恰好一个基础PE加独立C/D，不是阵列。参数从这两个顶层显式传入全部基础PE。输入是固定物理槽位，实际模式禁用不支持的PE并屏蔽其数值/special；软件需要按活动PE组织逻辑K区间，不能假定inactive槽被自动压缩。

| 配比 | K方向示例 | H/Q/E native K |
| --- | --- | --- |
| 1:2:4 | HQE_g4 | 16/32/64 |
| 1:2:6 | HQE_g4+E_g2 | 16/32/96 |
| 1:2:8 | HQE_g4+E_g4 | 16/32/128 |
| 1:4:8 | HQE_g4+QE_g4 | 16/64/128 |

这是互斥模式的每次接收容量比，不是面积比。相同总容量可对应不同物理布局，必须保留完整layout与配置hash。MN/阵列方向的多输出、广播和调度继续属于后续审核范围。

## 证据边界

编译/CHIRRTL/split RTL及有限定向smoke见 [six-pe-checks.md](six-pe-checks.md)。定向smoke只检查单位scale、−1/0/+1产品的结果坐标与11级valid，不能代替全格式/scale/舍入/严重抵消/随机数值参考回归。导出保持generated、rtl_test=not_run、ppa_eligible=false；未运行DC/power，未生成面积功耗数字。
