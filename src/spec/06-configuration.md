> 功能：定义参数及其合法派生关系；范围：构建参数、模式容量、位宽和频率规格常量；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../cmodel/README.md)、[Chisel](../chisel/README.md)、[Verilog](../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# 参数与配置合同

~~状态：首批参数与关系已定义；具体 schema、默认 K 和未决参数待定。下列名称是 spec 的统一符号，不代表已实现 API。~~

状态：当前主配置 k_fp16=16、合法变体 K4/K8/K16 已明确；格式/结构常量与派生公式按 v1.1 参数合同集中管理。配置 schema、扫描合法范围及未来扩展 profile 尚待冻结，当前没有已实现 API。

## 集中参数与约束

| 参数/规格常量 | 本轮值或约束 | 性质 |
| --- | --- | --- |
| `group_rows` / `group_cols` | 4 / 4 | 当前广播组结构参数；其他取值待批准 |
| `group_stack_count` | 4 | 竖直组数；当前水平方向只有一组 |
| `k_fp16` | 4、8、16；主配置取 16 | 构建期参数；对应 K4/K8/K16 |
| `base_group_fp16_k` | 4 | 固定基本组基准；T2H4Q8E16 |
| `elements_per_lane[T/H/Q/E]` | 1/2/4/8 | 每组拆两 lane，每 lane T1H2Q4E8 |
| `group_count` | `k_fp16/base_group_fp16_k` | 1/2/4 个并行基本组 |
| `group_sum_growth_bits` | `ceil(log2(group_count))` | 0/1/2 位自然增长 |
| `scale_group_elements` | 16 E 元素 | scale/HiF4 metadata 物理分组参数 |
| `k_mode(mode,k_fp16)` | `(k_fp16/4)*2*(1/2/4/8)`，T/H/Q/E | INT8 与 Q 同并行度；由 lane/formula 派生 |
| `unpack_input_atom_bits` / `unpack_exp_bits` / `unpack_mantissa_bits` / `unpack_sign_bits` | 16 / 10 / 16 / 4 | 固定解包字段规格常量；H1/Q2/E4，T 占 32 位容器 |
| `tf32_input_bits` | 32 | 输入容器规格常量，不改变 TF32 数值精度 |
| `retain_main_bits` | ≥25 | 主浮点模式保留目标；计数口径待定 |
| `retain_fp4_bits` | 基准 35 | MXFP4/NVFP4 保留目标；可探索范围待定 |
| `retain_hif4_bits` | 初始目标 37 | HiF4/NVFP4 共享路径推导后确认 |
| ~~`max_dp_pipeline_stages`~~ | ~~8~~ | ~~输入到输出深度上限，不可为时序任意放宽~~ |
| `max_dp_pipeline_stages` | 默认8；仅 post_scale_norm_extra_stage=1 的备用 profile 为9 | 用户允许为 scale 后规格化拆一级；不任意增加周期 |
| ~~`latency_by_mode` / `ii_by_mode`~~ | ~~待定义，L≤8~~ | ~~实现结果及协议合同，不得与 K 混淆~~ |
| `latency_by_mode` / `ii_by_mode` | 当前全格式 L=8，II=1 目标 | 结构与时序仍待验证；不得与 K 混淆 |
| `target_frequency_hz` | 1_410_000_000 | 当前时序目标；周期由此派生 |
| `supported_modes` | TF32、FP16、BF16、MXFP8/6/4、NVFP4、HiF4、INT8 | 功能范围；HiF8 排除 |
| `int8_bypass` | 允许评估，选择待定 | 构建期候选；不能当作已存在路径 |

## DP 容量派生

- 基本组为 `T2H4Q8E16`，由两个 `T1H2Q4E8` lane 构成。
- `base_group_count=k_fp16/4`，故 K4/K8/K16 并行使用 1/2/4 组。
- 对模式 T/H/Q/E，`k_mode=base_group_count*2*elements_per_lane[mode]`，lane 项数为 1/2/4/8。K16 得到 T8H16Q32E64。
- E 模式计算组数由 `k_mode(E,k_fp16)/scale_group_elements` 推导；MXFP4 每两个相邻槽共用 scale、HiF4 E64 四槽共用一个 scale，NVFP4 各槽独立。MXFP8/6 的每基本组为 Q8，32 项块 scale 在四个基本组物理槽广播，短 K 使用所属块的子片段。
- K 组和树自然增长 `ceil(log2(base_group_count))` 位；组数为 1 时增长为 0。

## TensorCore 统一派生

- `group_dp_count=group_rows*group_cols`，当前 16。
- `tensorcore_rows=group_rows*group_stack_count`，当前 16。
- `tensorcore_cols=group_cols`，当前 4。
- `tensorcore_dp_count=group_dp_count*group_stack_count`，当前 64。
- `target_period_ns=10^9/target_frequency_hz`。
- 总线宽度从元素容器、模式容量、scale/metadata 布局派生；控制宽度从实际范围推导，单元素/单状态边界明确处理。
- 普通定宽整数乘法的精确结果宽度从两个操作数宽度求和；规约增长根据项数与取值范围推导。浮点对齐、scale、C 合并还需要独立的位宽证明，不能直接套用一个全局公式。

## 禁止魔鬼数值

CModel、Chisel、手写 Verilog 和 testbench 使用相同的有效配置。规格常量集中命名，派生量只从定义计算，不在多个模块重复写 16、64、25、35、37 或流水延迟字面值。

“所有值参数化”包括命名的固定格式常量和有依据的派生表达式，不意味着可以随意改变标准格式编码或把每条局部连线都变为独立自由参数。参数须有单位、作用域、来源、合法性和默认状态；尚未决定的值保持未指定，不能以 0 或旧版值代替。

~~非法 K、HiF8 模式、低于明确精度下限或超过 8 级的候选不得静默降级。~~

**v1.1 当前定义：** 非法 K、HiF8、低于精度下限或当前基线超过八级都不得静默降级；未来源扩展增加 1–2 级必须以另行批准的 profile 显式记录。精度计数口径等未闭合项在实施前必须解决，不能仅通过“参数检查”伪装为已验证设计。

## v1.1：参数对象与资源公式

所有模块由构造参数接收有效参数对象，计划在 `src/chisel/parameter/` 定义（未创建文件），生成期做合法性检查；输入配置与实际派生结果进入后续 manifest。CModel/手写 Verilog/TB 读取同一有效配置。

| 具名量 | 定义或当前初值 | 派生用途 |
| --- | --- | --- |
| lanes_per_base_group / mul_groups_per_lane | 2 / 2 | 基本组与乘法器组实例数 |
| mul_hi_bits / mul_lo_bits | 8 / 4 | HH/HL/LH/LL 原始乘积和位移 |
| ~~local_align_fraction_bits~~ | ~~当前 25，至少 25~~ | ~~小数保留位；局部幅值宽=乘积整数位+该值~~ |
| local_shift_mag_width | 可调无符号窗口，默认 27 | S3 固定共享移位器位宽，实例统一接收参数 |
| local_align_fraction_bits | local_shift_mag_width-product_integer_bits，当前至少 25 | 派生量，不与窗口作为两个独立输入 |
| global_signed_align_width | 初值 40，可扫参 | 包含符号；幅值窗口为该值减一 |
| hif_e1_bits / hif_e2_bits | 1 / 1 | 局部幅值与剩余指数范围 |
| e_exact_guard_bits | 2×(2^hif_e2_bits-1) | 先补低零保证 HiF4 局部移位精确 |
| tree_depth(n) | ceil(log2(n))，n=1 为零 | 递归生成平衡树，不要求 n 为二次幂 |
| top_fanin | group_count+1 | 包含 C；2/3/5 项对应深度 1/2/3 |
| top_sum_width | global_signed_align_width+tree_depth(top_fanin) | 默认 41/42/43，完整保留增长 |
| local/global_shift_control_bits | ceil(log2(window_width+1)) | 完整比较 delta 后饱和，不截断 delta 造成回绕 |
| int8_input_bits / int32_bits | 标准格式常量 8 / 32 | INT8 幅值范围及 INT32 回绕模数 |
| ~~latency_fp / latency_int~~ | ~~当前 8 / 8~~ | ~~模式会话共享输出寄存边界~~ |
| latency_fp / latency_int | 当前 8 / 8 | 逐请求格式控制，共享固定输出寄存边界 |

计数器/指数/anchor 的宽度从最大值和有符号范围推导。8+8 的指数和必须保留第九位，5+5 保留第六位；scale 指数和也是九位。上表实际值和 [逐级布局](dp/numeric-layout.md) 中的 27/15/30/31 仅作默认配置的推导展示，不在算术模块中重新硬写。窗口合法范围由输入位宽与精度条件决定，不自行填一组扫描上下限。

## v1.1：当前与未来 profile 的延迟约束

~~当前主配置 `H16Q32E64（TF32=T8）` 的 latency_fp/latency_int=8，max_dp_pipeline_stages=8；K4/K8 的派生变体同一固定输出周期。未来专用 Q/E/QE 输入源必须另定静态 source profile；全局物理扇入数=实例化来源数+1（C），生成树的深度按该物理扇入数计算。模式能力掩码不改变本 profile 的固定周期。只有用户批准的未来扩展 profile 才能定义 9/10 级上限及对应 valid/last 延迟，当前不开放或实现这些配置。~~

**v1.3：** 默认所有K/格式L8；本次允许为scale后检测/指数准备单独形成L9备用。未来专用增源的9/10级另定profile，不与本例外自动叠加；均未实现。

## 历史修订对照

以下为本次版本化时恢复的历史草案对照；删除线内容已被替代，不作为当前实现依据。较早内容尚无正式版本号，来源按真实提交或用户确认记录，不追认其为已批准合同。

- **Q scale 广播更正**：~~MXFP8/6 32 项块 scale 按两个 E 槽广播。~~ → **当前：**每个基本组为 Q8，Q32 的同一 scale 在四个基本组槽广播；短 K 使用原块子片段。（来源：dba8ecf → 42350c5，修正文档笔误）

## v1.2：接口与控制参数

A/B datatype 枚举、C/D 类型、scale 类型及编码集中定义，默认位宽 4/1/2；端口尺寸从 k_fp16、G 和格式容器推导，见 [DP 接口](dp/interface.md)。mode_session/active_mode 不再是构建参数或运行状态。各级 r/alpha/A 范围、SOP 格式、移位/树参数关系见 [出口表](dp/stage-formats.md)；所有减法临时位宽由完整范围推导。局部 W 改变时连同后续槽宽和全局 pad 合法性一起重新检查。

## v1.3：规格化与 scale 的派生参数

`post_scale_norm_extra_stage` 是构建期0/1，默认0；latency_fp=latency_int=8+该值，备用1须有时序选择记录。该条件例外补充旧“只有专用增源 profile 可超过8级”的限制，不能动态逐笔切换。

group_lzd_input_bits=M_group；group_lzd_count_bits=uwidth(M_group-1)，另有zero标志。S5不做动态左移，原F按模式保留；逻辑规格化F=M_group-1只用于推导。global_net_shift_bits按signed z-d或A_raw-E_max中间范围派生；双向shift_amount宽度为uwidth(M_global)，方向独立。anchor 范围从 A_raw 范围减最大非零 clz 推导；delta_bits=uwidth(e_max-e_min)，减法临时宽度单独推导。NV/HiF 的结构零删除量、紧凑 SOP/scale/乘积宽度及共享乘法最大宽度按 [scale 公式](dp/scale.md) 计算。默认13/15、8/6、21和15×8均是推导结果，不增加互相独立且可能矛盾的手填宽度旋钮。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T15:13:43+08:00 | 历史记录 | 建立新版规格目录骨架与历史归档边界。 | [e8e07c2](https://github.com/Futuresxy/DP-Puzzel/commit/e8e07c2) |
| 未编号（追溯） | 2026-11-04T15:43:59+08:00 | 历史记录 | 记录 TensorCore/DP-Group/DP 首批架构、数值和时序要求。 | [76d31f2](https://github.com/Futuresxy/DP-Puzzel/commit/76d31f2) |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 补充 v1.1 相关资源、数值或验证合同。 | 用户架构图与补充；[总时间线](CHANGELOG.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 同步本轮接口、C 解包阶段、逐请求控制或资源/验证合同；保留被替代定义。 | 用户本轮要求及确认；[总时间线](CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 按用户最终选择，S5 scale后LZD仅计数、S6一次双向移位；同步数值/接口/资源/备用周期，保留对照。 | 用户最终双向移位选择；[总时间线](CHANGELOG.md) |
