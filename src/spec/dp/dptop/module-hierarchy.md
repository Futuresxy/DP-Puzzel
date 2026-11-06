> 功能：定义 DP 模块层级与未来 S6 接入合同；范围：T1H2Q4E8、T2H4Q8E16、H16Q32E64（T8）与后续专用源；版本：v1.6；修改时间：2026-11-06 12:06:08 +08:00；对应代码：[CModel lib/detail.hpp](../../../cmodel/lib/detail.hpp)；分组主方案手写 RTL：[dp_top.v](../../../verilog/top/dp_top.v)；Chisel 尚未实现。

# 模块层级、所有权与 S6 扩展点

状态：当前用户指定模块化层级 `T1H2Q4E8 → T2H4Q8E16 → H16Q32E64`；顶层名称省略 T，但保留 TF32 T8。只描述当前主配置，未来 Q/E/QE 专用源的功能与数据布局待单独批准；现用 CModel 与手写 Verilog 已实现 v1.5 的无符号 scale；SystemVerilog 保留该版本作为冻结的历史参考。E 专用 CModel 已实现并复用公共 S5–S8，E 专用 RTL 已实现并通过验证；Chisel 和其他未来专用源待实现。

## 1. 当前层级与周期所有权

```text
H16Q32E64（TF32=T8；参数化 K4/K8/K16 的顶层 DP）
├── 逐请求 ctrl/valid/last；C raw32 传递 S1–S4、S5 FP32/INT32 解包
├── T2H4Q8E16 × group_count（主配置四组）
│   ├── 本组 scale/metadata 解包（S1）、scale 预计算（S2）
│   ├── 基本组共同指数 MAX（S2），返回两条 lane
│   ├── T1H2Q4E8 lane[0]（A/B S1 解包；S2–S4 局部计算）
│   ├── T1H2Q4E8 lane[1]（相同边界）
│   └── 两 lane 合并、符号/幅值分离、无符号 scale、组输出（S5）
├── S6：组 token + C 的有效 anchor MAX、幅值 RTZ 与符号恢复
├── S7：group_count+1 项共享规约树
└── S8：FP32 RNE / INT32 回绕，valid/last 输出
```

三层是同一次 DP 计算的组合/寄存边界分工，不是每层各串联八周期。统一按时钟沿更新前观察握手：顶层在沿 n 接收，S1 在该沿更新，S8 在沿 n+7 更新；下游/TB 在沿 n+8 更新前采样该输出，故接收至输出观察为 L=8。局部 S4 对应沿 n+4 的更新前观察。最外部仅一次 A/B/C 原子握手，内部为固定推进的 valid 数据路径，无独立 ready 停顿；全局 `rst_n` 及逐请求 ctrl/last 遵循控制合同。

## 2. T1H2Q4E8

拥有 A/B 局部解包与分类、两套乘法器组、S2 的本 lane 元素指数候选、S3 对齐/符号化/E pair，以及 S4 四路共享树。输入为一个 lane 的完整原始容器、模式、适用的 e1/e2、有效位与事务控制；各输入的槽数随模式解释，不复制接口数值含义。

S4 输出局部补码 SOP、公共 r、zero/special 及本笔 ctrl/valid/last。F/位宽由参数与本笔格式解释，不需要把每个静态常量作为端口；所有动态选择必须读取同行控制，不能依赖会话固定或当前顶层 datatype。

T/H/Q 的 S3 对齐参考取自基本组公共 MAX，不能各 lane 自行选择局部 MAX 后在 S5 直接相加。HiF4 每 lane 的 e2 仍按所属 8 元素共享。

## 3. T2H4Q8E16

拥有两条 lane 的打包分发、组共同 MAX、块 scale 解包/预计算及 S5 合并与系数乘法。其 S5 对外 token 包含独立符号、无符号幅值、anchor/二进制坐标、zero/special、valid 与对应事务控制。幅值宽度与 F 按数值合同推导，顶层不能猜测固定小数点。

跨 lane MAX 是 S2 内的标量侧接口：lane 从已注册的 S1 字段产生 `exp_candidates_comb/active_comb`，组模块组合选择 MAX，再经 `group_max_comb` 返回；S2 边界注册所需的指数/参考值。产生候选指数不依赖返回 MAX，故数据依赖无环。可拆为明确的算术子模块，但不能在 module 端口处暗加寄存器，导致 MAX 迟一拍。

scale 指数/系数可以提前准备；S5 的数据求和、实际零判定和 sign/magnitude 转换仍需同拍预算。未选中的乘法、移位及 scale 数据通路通过参数/模式使能隔离。

## 4. H16Q32E64 顶层

当前四个基本组形成 T8H16Q32E64。顶层拥有逐级请求控制、C raw32 的 S1–S4 传递和 S5 解包、S6 组+C 对齐、S7 完整树以及 S8 输出；每笔独立完成 dot+C，无会话锁定。C 不复制进每个基本组。

S6 是未来扩展的接入边界。新增源必须表示同一事务、同一输出位置的点积贡献，并与当前组 token 使用相同语义字段。若用于增加 K 容量，活动源容量相加后重新定义模式 K、A/B 打包及 scale 归属；若新增独立 M/N 输出，则不应接入同一个标量 SOP 规约，而需另定上层输出组织。

## 5. 专用源与未来组合边界

E-only 的 dp_top_e 已通过独立前端接入一套后端。后续可在同一顶层 S6 前混合增加仅 Q、仅 E 或 QE 专用源，混合组仍未实现。这里的“第六级增加”是接入额外的部分和输入，不将完整乘法计算塞进 S6；专用源先完成自身前端，按约定到达阶段提供 sign/magnitude token。

- 按源列表/能力集生成活动输入掩码。某模式不支持的源不贡献值、指数或特殊状态；QE 的 Q/E 是互斥模式能力，不能同时加总峰值。
- 每个源声明容量、输出数值坐标、延迟与有效位。先匹配事务、mode、输出坐标和 last，必要时插入有明确延迟的同步寄存；不能拼接不同请求或不同 mode 的 token。
- 物理规约扇入数为 `N=instantiated_source_count+1`（包括 C），生成树深 `ceil(log2(N))`；模式能力掩码可以屏蔽无效源，但不动态改变已生成的树/固定流水。宽度增长、MAX 拓扑和移位器数量由同一源配置推导。
- 若源数增长导致关键路径过长，未来扩展 profile 可增加 1–2 级，例如拆开 MAX/delta/shift 或规约树。新增周期位置、各源补拍、输出 L、valid/last 排空及功耗比较必须另写合同。

主配置仍优先 L8；必要时允许独立 L9 检测/指数准备 profile。专用源扩展仍待单独定义，不能混淆各 profile 验收。

## 6. 参数与观察点

顶层向基本组、基本组向 lane 传入已校验的参数对象；各层只从自身项数、格式宽度、保护位和父层有效配置派生局部结构。参数对象计划置于 src/chisel/parameter/，尚未创建。共有公式和格式常量集中定义，禁止三层各写一套 局部/全局窗口、紧凑 SOP 宽度 或树深常量。

CModel 应按同一模块边界提供 S1 解包、S2 MAX/产品、S3 移位、S4 lane 和、S5 组 token、S6 对齐、S7 总和、S8 输出的 trace。数学参考独立评价误差；CModel 已提供这些观察点；手写 RTL 的 S1–S7 观测与模型比较见 [实现合同](../implementation/verilog.md)。

## 7. 功能模块边界与源码映射

[DP 接口](interface.md) 统一列出顶层信号、datatype 编码与内部同拍 token；[功能统计](../implementation/resource-accounting.md) 定义乘法、指数/MAX、移位、树、scale、解包和 LZD/norm/RNE 等逻辑模块 ID。后续各功能模块单独映射 Chisel、手写 RTL 和网表实例，统计区域明确拥有的寄存/mux，保留八级边界；当前已有 CModel 与 [手写 RTL 源码映射](../implementation/verilog.md)。S3 按 [移位器共享](../lane/shifter-sharing.md) 由输入 mux 驱动四个固定 W-bit 实例。

## 8. 基本组与全局边界更新

基本组 S5 先分离组和的符号与幅值，再做 scale 或旁路并用 LZD 计数，输出原幅值/A_raw/z；顶层 C 解包与子正规计数并行。顶层 S6 生成 e、MAX 和 net 并一次双向移位，S7 树、S8 编码。未来专用源也须声明原坐标及 z 或可转换等价字段；不得接错已规格化/未规格化 token。必要时 L9 拆检测/指数准备，原 S6 接入边界顺延，详见[流水](pipeline.md)。

## 9. DP 设计族的工程组织建议

状态：CModel 已提供静态 frontend=multi/e 选择、独立 E lane/group 和共用后端；E64 配置位于 src/configs/dp/e64.json。下面的通用组合框架仍为建议，E RTL 提供独立 dp_top_e 与 files_e.f；groups 列表、混合组和通用后端寄存模块抽取尚未实施。已冻结 SV 的范围保持不变。

建议统一为“共用基础库 + 分类型模块 + 组合配置”。multi/e 表示构建时选择的硬件实现类型；datatype 表示请求运行时的数值格式，二者分别管理。不同类型在同一仓库开发，共享基础模块与文档，顶层按静态 profile 组合；Git 分支继续用于经用户同意的并行任务。

| 分类 | 统一维护的内容 | 类型差异放置位置 |
| --- | --- | --- |
| 基础库 | 固定功能算术、scale/C 解码、LZD、移位核、舍入、协议与参考 | 只有语义相同且参数可表达时才复用同一模块 |
| lane | 一份层级入口和明确的接口/周期要求 | lane/multi 与 lane/e；E 保留自己的 S2 pair/S3 树实现 |
| group | scale/组 token 的公共合同 | group/multi 与 group/e；各自完成前端数值坐标 |
| dptop | 共用 C 路径、S6–S8 后端和请求组织 | 薄顶层按 profile 选择 group 类型、数量及路由 |
| profiles | 单一来源的构建参数和模块组合 | 建议 src/configs/dp/，同时供 CModel、RTL 构建和测试读取 |

以下为组合说明；multi/e64 均有 CModel 和纯 Verilog 顶层，混合组尚未实现：

| 示例 profile | 组构成 | 模式容量 |
| --- | --- | --- |
| multi_t8h16q32e64 | 4×multi group | T8H16Q32E64 |
| e64 | 4×E group | E64，支持 MXFP4/NVFP4/HiF4 |
| mixed_t4h8q16e64 | 2×multi group + 2×E group | T4H8Q16E64；INT8 与 Q 同并行度 |

profile 只填写独立参数，按类型能力及组数派生各模式 K、活动源、输入位切片、量化块 scale 广播、树扇入与增长位。不同时手填相互矛盾的组数/K/总位宽；兼容组幅值宽继续按现有 LOCAL_W 关系推导。当前仅用 K_FP16 固定推导所有模式容量的 Config 不能直接表达任意混合组合，需要在后续实施中扩展。

优先的组合边界是 S5 group token：不同 group 交付相同字段宽度、数值语义及到达拍，后端按 magnitude/A_raw/z 处理，允许不同类型的 F 坐标。lane 只有在数值和寄存边界均兼容时才可互换；现有 multi lane 与 E 候选的切点不同，应分别由匹配的 group 使用。已完成 FP32 舍入的两个 DP 输出不作为保持原精度的 K 部分和直接相加；扩大同一标量点积应在最终舍入前合并各组，并且只加一次 C。不同 M/N 输出各保留自己的后端。

混合 profile 仍按同一请求同 datatype 的原合同处理。上层须根据组的静态能力生成该请求的参与掩码，数据和指数 MAX、special、零符号规约统一排除不支持该模式的源；不能只拉低一个局部 valid。有限非零指数候选与“参与运算但数值为零”的项分开处理。该 mask 的接入尚未实现，不能直接把新组合塞进当前顶层宣称完成。

代码共用与物理资源复用分别统计：多个实例可以引用同一个模块定义，每个实际实例仍各自占面积/活动成本。一个 DP 中的源列表共同使用一套后端；两个独立 DP 不因引用同一个后端文件就共享一份硬件。具体代码目录和迁移顺序见 [RTL 框架建议](../implementation/verilog.md#6-分类型模块与组合配置建议)，CModel 对应组织见 [模型框架建议](../implementation/cmodel.md#7-与-rtl-对应的设计族组织建议)。
