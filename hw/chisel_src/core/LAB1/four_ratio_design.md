# LAB1：基于 MidGroup 组合的四种算力配比实验

本实验以现有六种基础单元为组合边界，研究 H:Q:E = 1:2:4、1:2:6、1:2:8、1:4:8 的面积、时序和真实负载功耗。优先打通配置、RTL 导出、数值与周期验证、EDA 和结果记录，再根据测量结果优化微架构。

H 对应 BF16/FP16，Q 对应 MXFP8/6，E 对应 MXFP4/NVFP4/HiF4。H/Q/E 数字表示相应模式每次接收的 K 元素容量；多模式共享硬件的三项容量不能同时相加，也不是面积占比。HiF4 沿用当前源码语义，其规范来源/版本仍待确认。

本路线替代之前在一个 MidGroup 中混合 4/6/8 个 PEGroup 的方案。保留现有五族目录、六种基础 profile 和内部流水；LAB1 负责实验组织，配置放在 `hw/configs/`，RTL 只由统一入口导出到 `hw/rtl/`。当前不增加阵列、广播、L0 或跨事务 accumulator 电路。

## 1. 层级、组合边界和共用基线

讨论中的 MidGroup 对应当前源码中的基础 `PE_*_gN`，仍沿用现有类名和文件名：

```text
SubPE → PEGroup → 基础 PE（原 MidGroup）→ K_PE / MN_PE
```

| 基础 profile | H/Q/E 容量 | PEGroup 数 | 计算组织 |
| --- | --- | ---: | --- |
| PE_HQE_g4 | 16/32/64 | 4 | HQE 分级复用 |
| PE_QE_g4 | 0/32/64 | 4 | QE 分级复用 |
| PE_H_g4 | 16/0/0 | 4 | H 专用全局对齐 |
| PE_Q_g4 | 0/32/0 | 4 | Q 专用全局对齐 |
| PE_E_g4 | 0/0/64 | 4 | E 专用路径 |
| PE_E_g2 | 0/0/32 | 2 | E 专用半容量路径 |

这些基础单元均在 S11 输出 `{magnitude, negative, top_anchor, is_zero, special}`，不含最终 C/D 处理。公共 F=`pe_align_width`；E_g2 规范化后精确补一个低零，以保持统一坐标。H/Q 专用路径与 HQE/QE 分级路径的 RTZ 位置不同，接口相同不能作为数值误差相同的依据。

K_PE 接收 1–4 个基础单元的有序 layout，规约不同 K 区间，并共享一个 C 输入和一个最终 D 输出。MN_PE 接收一个基础单元，自带独立 C/D。两者都复用 [DotUnit.scala](../../Utils/DotUnit.scala)，合同为 18 级、同 batch II=1。

**LAB1 只保留两个 MN 补充类型：E64、Q32E64。** 单 HQE 的 MN 实例与 `K_PE([PE_HQE_g4])` 使用相同的数据通路组织，因此 1:2:4 共用 K 基线，不重复建立 MN_H16Q32E64 实验项。这里限制的是 LAB1 实验集合，通用 MN_PE 仍保留选择其他基础 profile 的能力。

## 2. 六种完整顶层与配置

下面四个 K 顶层和两个 MN 顶层即可构成本实验。顶层名称由配置生成，不另复制六套 Chisel 实现。

| 用途 | top | 有序 layout | 默认 RTL 顶层名 | 配置 |
| --- | --- | --- | --- | --- |
| 共用 1:2:4 基线 | k | HQE_g4 | K_PE_H16Q32E64 | [k_1_2_4.json](../../../configs/k_1_2_4.json) |
| K 扩展 1:2:6 | k | HQE_g4, E_g2 | K_PE_H16Q32E96 | [k_1_2_6.json](../../../configs/k_1_2_6.json) |
| K 扩展 1:2:8 | k | HQE_g4, E_g4 | K_PE_H16Q32E128 | [k_1_2_8.json](../../../configs/k_1_2_8.json) |
| K 扩展 1:4:8 | k | HQE_g4, QE_g4 | K_PE_H16Q64E128 | [k_1_4_8.json](../../../configs/k_1_4_8.json) |
| MN 补充 E64 | mn | E_g4 | MN_PE_H0Q0E64 | [mn_e_g4.json](../../../configs/mn_e_g4.json) |
| MN 补充 Q32E64 | mn | QE_g4 | MN_PE_H0Q32E64 | [mn_qe_g4.json](../../../configs/mn_qe_g4.json) |

表中省略了 layout 字符串的 `PE_` 前缀，JSON 使用完整 profile 名。原 `full_h16q32e64.json` 是 `top=mn` 的历史配置，LAB1 使用显式 `top=k` 的新基线。已有的 `mn_q_g4.json` 是 Q 专用示例，不计入本实验的两个 MN 补充类型。

## 3. 三种新增配比的 K/MN 实现对比

令 B 为完整 K 基线 `K_PE_H16Q32E64`，E 为完整 `MN_PE_H0Q0E64`，QE 为完整 `MN_PE_H0Q32E64`。下表以整数实例配对，使每行两侧的总 H/Q/E 容量一致。

| 目标配比 | K 方向的完整单元组合 | MN 方向的完整单元组合 | 两侧总 H/Q/E 容量 | 物理 C/D 路数：K / MN |
| --- | --- | --- | --- | --- |
| 1:2:6 | 2 × K_PE_H16Q32E96 | 2 × B + 1 × E | 32/64/192 | 2 / 3 |
| 1:2:8 | 1 × K_PE_H16Q32E128 | 1 × B + 1 × E | 16/32/128 | 1 / 2 |
| 1:4:8 | 1 × K_PE_H16Q64E128 | 1 × B + 1 × QE | 16/64/128 | 1 / 2 |

1:2:6 的 K 单元使用 E_g2 增加 K32；MN 侧使用一个完整 E64 输出单元服务两个基线位置的增配需求。`2 × E_g2` 与 `1 × E_g4` 虽然总 E 容量相同，内部规约、规范化和控制数量不同，面积/功耗不能预先视为相等。

若基线有 P 个输出位置，MN 侧的 1:2:6、1:2:8、1:4:8 分别增加 P/2 个 E、P 个 E、P 个 QE；首项要求 P 为偶数。这只是实例集合的实验定义，不代表已实现物理阵列。

K 扩展中，每个活动基础单元计算一个不重叠 K 区间的部分点积，所有部分结果和同一个 C 在顶层对齐、相加，最终舍入得到一个 D。H 模式只启用 HQE；1:2:6/1:2:8 的 Q 模式也只启用 HQE；1:4:8 的 Q 模式同时启用 HQE 和 QE；E 模式启用全部单元。

MN 扩展中，每个完整单元计算自己的输出位置，拥有独立 C 和 D。E 单元在 H/Q 实验中不承担计算，QE 单元在 H 实验中不承担计算；其静态成本和实际 idle 活动仍需计入。MN 侧相加的是物理实例成本，各个 D 不在硬件中相加。

| 比较项 | K 扩展 | MN 扩展 |
| --- | --- | --- |
| 增配位置 | 同一输出的 K 规约路径 | 更多独立输出位置 |
| 基础单元内部 | 保留各自 S11 规范化边界 | 保留各自 S11 规范化边界 |
| 顶层运算 | 多个部分点积 + 一个 C | 各单元分别完成一个部分点积 + 各自 C |
| C/D 成本 | 每个 K 顶层一套 | 每个独立输出单元一套 |
| 输入组织 | 按有序 layout 划分固定物理槽 | 各完整单元独立组织输入 |
| 首轮分析边界 | 完整 K_PE 单元 | 基线和两类 MN 补充单元的成本汇总 |

面积分别记录完整顶层及层次分解，按表中整数实例数汇总；保留不同 native K 对实际 GEMM 映射的影响。相同总 MAC/cycle 容量不能直接证明同一 workload 完成时间相同。

功耗应在相同工艺/PVT、频率、格式、负载来源和明确的活动窗口下比较；根据各单元实际 active/idle 时间汇总，不能把三个模式的满载峰值同时相加。跨周期复用同一输出的 C 需要由测试/软件调度显式处理依赖，不能假定 II=1 意味着上一条 D 已可反馈。

首轮结果明确排除阵列级广播、互连、L0、布局布线成本；若后续补入这些成本，应单列来源和边界。时序未达到目标时钟的候选须报告实际时序状态，不能继续按达标频率解释功耗或吞吐优势。

## 4. 用 1:2:4 跟踪参数如何构建硬件

### 4.1 生成时配置

基线 [k_1_2_4.json](../../../configs/k_1_2_4.json) 的内容为：

```json
{
  "schema_version": 2,
  "top": "k",
  "layout": ["PE_HQE_g4"],
  "alignment": {
    "q_align_width": 28,
    "group_guard_bits": 2,
    "pe_align_width": 40,
    "top_align_width": 40
  }
}
```

[Parameters.scala](../../config/Parameters.scala) 通过 `DesignConfig.load/fromJson` 解析 JSON。默认值 < JSON < CLI，最终全部有效参数写入导出 manifest。构造时 `require` 检查 profile、layout 数量及位宽：Q 窗口 26..30，PG guard 2..4，PE/top 窗口 38..48，top 不小于 PE 窗口。

`PEConfig("PE_HQE_g4")` 派生 `groupCount=4`、`wordCount=16`、`h=16`、`q=32`、`e=64`。`DesignConfig` 汇总 layout 后得到 `wordCount=16`、`capacity=H16Q32E64`、`topName=K_PE_H16Q32E64`。默认窗口下没有参数后缀；非默认窗口名称追加 `_Aq...g...p...t...`。

### 4.2 实例化层级与端口

[Elaborate.module](../../elaborate/Elaborate.scala) 根据 `top=k` 调用 `new K_PE(config.layout, config.alignment)`。[K_PE](../K_PE.scala) 继承公共 `DotUnit`，`DotUnit` 遍历 layout，通过 [PEFactory](../../Utils/PEFactory.scala) 实例化一个 [PE_HQE](../../pe/PE_HQE/PE_HQE.scala)。

```text
K_PE_H16Q32E64                     # DotUnit 的电路直接属于此顶层
├── PE_HQE_g4                      # 一个基础 PE / MidGroup
│   ├── 4 × PEGroup_HQE
│   │   ├── DataUnpack_HQE
│   │   └── 4 × SubPE_HQE          # 总计 16 个 SubPE
│   └── PEAlignNormalize
├── CUnpacker
├── LzdNormalize
└── RoundPack
```

每侧 A/B 有 16 个 16-bit 数据字。每字按模式容纳一个 H、两个 Q 或四个 E 元素，因此同一物理输入支持 K16/K32/K64；FP6 仍按每 byte 低 6 bit 存储。每侧还分配 4 个 scale 槽、16 个 group0 位和 8 个 group1 位，具体使用方式由格式决定。

[PEWiring](../../Utils/PEWiring.scala) 将每连续 4 个数据字送入一个 PEGroup，并按格式选取 scale。H 不需要块 scale；Q 使用基线的第 0 个 scale；MXFP4 使用第 0/1 个 scale，NVFP4 每组一个 scale。HiF4 的主 scale 和 group bits 遵循当前源码合同。

多基础单元的 K 配置按各自 wordCount/groupCount 的前缀和切分数据及 scale 槽，inactive 槽不自动压缩。扩展到 Q64 等配置时，每个基础单元有自己的局部 scale 槽，测试驱动必须按这一物理布局填充。

### 4.3 运行时配置与接收

生成时参数决定实例和位宽；硬件端口 `in_cfg` 决定某个 batch 的 A/B 格式、scale 类型、C 格式、舍入模式和输出类型。运行时配置不改变物理实例数量。

顶层按 `Idle → Accepting → Draining` 工作。Idle 时接受 cfg；Accepting 时 A/B 与 C 原子握手，每次共同 fire 接收一个事务；接受 `last` 后停止输入，最后一个 D 排出后返回 Idle。输出为 Valid-only，没有结果反压。C 可选择 FP32/FP16/BF16，当前最终 D 只支持 FP32。

### 4.4 数据计算与输出位宽

| 流水边界 | 基线操作 | 默认位宽/数量 |
| --- | --- | --- |
| S01–S07 | 解包、SubPE 计算、PEGroup 局部对齐和 scale | 4 个 PG；PG 数据载体默认 W33 |
| S07–S11 | 跨 PG 的 MAX、对齐、规约、规范化 | 一个结果：magnitude W41、sign 1、anchor W11，F40 |
| S01–S11 的 C 支路 | 原始 C 延迟 9 拍，再解包 2 拍 | 与部分点积在 S11 会合 |
| S12 | 点积与 C 比较 anchor、生成移位量 | `termCount=1+1=2` |
| S13 | 对齐两个操作数 | `crossAddWidth=top_align_width+2=42` |
| S14 | 平衡加法、自然位宽增长 | `topSumWidth=42+ceil(log2(2))=43` |
| S15–S16 | 规范化、尾数提取与 sticky | 供最终舍入使用 |
| S17–S18 | 舍入和打包 | 一个 32-bit FP32 D，附 valid/last |

S11 基础结果的数值定义为 `(-1)^negative × magnitude × 2^(top_anchor - pe_align_width)`。这里的 W42 指 sign 和 magnitude 合计，anchor、zero、special 单独传输。

若把 PE/top 窗口改为 44/44，则基础结果 magnitude 为 W45、公共操作数 W46、基线顶层和 W47；最终 D 仍是 32-bit FP32。窗口控制内部保留精度，不是最终输出编码宽度旋钮。现有有限窗口对齐包含 RTZ，不能将该计算路径描述为任意长度的精确 FMA。

对于三种双基础单元 K 扩展，顶层 `termCount=2+1=3`，默认和宽度自动成为 `42+ceil(log2(3))=44`。每个基础单元仍保持自身 S11 输出，顶层继续采用 S18 输出合同。

### 4.5 展开和 RTL 导出

从仓库根目录进入 `hw` 后，先做结构展开：

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate config configs/k_1_2_4.json
```

选择已安装的 firtool 1.62.0 后，通过统一入口生成 RTL；下面工具路径为占位，需替换为本地实际目录：

```sh
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/k_1_2_4.json "LAB1 1:2:4 baseline"
```

窗口扫描直接使用 CLI，例如：

```sh
mill -i pe.runMain dp.elaborate.Elaborate config configs/k_1_2_4.json --pe-align-width 44 --top-align-width 44
```

[Generate.scala](../../elaborate/Generate.scala) 调用同一个 `Elaborate.module`，使用 split Verilog 导出到 `hw/rtl/K-PE_H16Q32E64_<MMddHHmm>/`。时间按 Asia/Singapore，已有同名目录拒绝覆盖。目录内包含 `README.md`、`manifest.json`、`files.f` 和 `src/*.sv`；manifest 记录完整参数、有序 layout、源码/config/RTL 指纹、工具版本和模块映射。

生成的 SystemVerilog 是配置特化后的硬件。修改 JSON/CLI 后必须重新导出；生成成功仅标记 `generated`，不代表数值或周期验证通过。

## 5. 实验交付与当前证据

本次更新实验路线及缺少的三个配置，复用现有 K_PE/MN_PE/六种基础单元，不改变 Chisel 电路。三个新增配置为 K 1:2:4、MN E64、MN Q32E64；三种 K 扩展继续使用已有配置。

本批已检查六份实验 JSON 的字段/默认窗口与容量、三组 K/MN 容量配对，以及文档本地链接、代码围栏和空白格式。当前会话的 PATH 中没有 Mill，未运行新增配置的 Chisel 展开、RTL 导出或仿真；上述命令是后续运行入口。

现有 [检查记录](../../../spec/six-pe-checks.md) 包含编译/展开/结构检查，以及基础 PE 的有限 SV 定向检查。它不代表完整格式精度验证通过；K/MN 的一般数值、C/D 和完整 batch 协议仍待 RTL 回归。当前没有本实验的面积、时序或功耗测量。

后续按以下顺序形成可复现批次：

1. 对六个完整顶层分别导出，保留配置、源码和 RTL 指纹。
2. 以独立 reference 和 SV testbench 验证各自格式、scale、C/D、特殊值、严重抵消、随机输入，以及连续/气泡/复位/batch 排空；固定种子和误差合同。
3. 建立 export/hash/验证证据门禁，只有对应 RTL 完整通过后才允许 PPA。
4. 在挂载 EDA 环境中，使用相同库/PVT、时钟和 IO 约束测量面积与时序，再使用匹配负载活动分析功耗。
5. 按第 3 节的实例组合汇总，分别报告面积、功耗、时序状态、每模式容量与 workload 完成延迟的适用边界。保存小型结果摘要，大型产物保留归档位置和 hash。

工艺/PVT、目标时钟、真实 workload 和 HiF4 规范版本等尚未确定项见 [roadmap](../../../../docs/roadmap.md)。不能用未校准估计填充测量栏，也不能把配置生成成功称为硬件验证完成。
