> 功能：定义 DP 顶层和模块接口；范围：端口/编码、原子握手、逐笔 datatype、内部 token 和历史对照；版本：v1.3；修改时间：2026-11-04 21:03:38 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（对应模块文件未建，文件映射待定义）。

# DP 顶层与模块接口定义

状态：当前 H16Q32E64（T8）及 K4/K8 变体的接口合同。用户确认 A/B 各自携带 datatype、首版仅同格式；C 在 S5 按 FP32/INT32 解包；每笔控制随流水推进，取消 DP 内会话锁定。原子 ready 表达式沿用现有候选，尚无实现验证。

## 运算和模块边界

浮点每笔计算有限位宽路径规定的 `scaled_dot(A,B)+C`，S8 以 RNE 输出 FP32；INT8 每笔计算有符号点积加 INT32 C，内部精确保留，S8 取低 32 位回绕。A/B scale 不作用于 C。DP 不持有跨请求 accumulator，不处理 C 的指令依赖。

三层为 T1H2Q4E8 → T2H4Q8E16 → H16Q32E64；主配置 k_fp16=16、G=4 个基本组。所有模式均 L=8，目标 II=1，无输出 ready。相邻请求可使用不同合法格式，last 仅是随请求传递的上层流标记。

## 构建期端口尺寸

令 `G=k_fp16/base_group_fp16_k`、基本组基准为 4、每组两个 32 位逻辑 lane：

| 字段规模 | 派生式 | K4 / K8 / K16 |
| --- | --- | --- |
| 每侧 A/B payload | k_fp16 × FP16 容器位数 | 64 / 128 / 256 bit |
| 每侧 scale | G × scale_container_bits，后者为 8 | 8 / 16 / 32 bit |
| 每侧 HiF4 e1 | G × (E16/每 e1 覆盖 4 项) | 4 / 8 / 16 bit |
| 每侧 HiF4 e2 | G × (E16/每 e2 覆盖 8 项) | 2 / 4 / 8 bit |
| C / D | FP32 与 INT32 共用编码容器 | 32 / 32 / 32 bit |

总线是 elaboration 后固定宽度，运行时 datatype 只改变同一总线的解释。TF32=K/2 个 32 位槽、H=K 个 16 位槽、Q/INT8=2K 个 8 位槽、E=4K 个 4 位槽，均占 16K bit。

## 顶层端口

| 信号 | 方向 | 宽度 | 合同 |
| --- | --- | --- | --- |
| `clock`, `reset` | 入 | 各 1 | 所有子模块共用；同步高有效 reset 仍为接口候选，复位取消所有在途请求 |
| `in_a_valid`, `in_b_valid`, `in_c_valid` | 入 | 各 1 | 三个源有效；datatype 与各自 payload 同属一笔 |
| `out_a_ready`, `out_b_ready`, `out_c_ready` | 出 | 各 1 | 只允许同拍原子接收，见握手公式 |
| `in_a`, `in_b` | 入 | 各 16K | 低位对应低元素索引，格式切片见下文 |
| `in_a_datatype`, `in_b_datatype` | 入 | 各 data_type_bits，当前 4 | 独立字段；首版必须为同一受支持格式 |
| `in_scale_a`, `in_scale_b` | 入 | 各 8G | 每个基本组一个原始 8 位 scale，广播由上层完成 |
| `in_scale_a_datatype`, `in_scale_b_datatype` | 入 | 各 scale_type_bits，当前 2 | 每侧本请求全部 scale 槽采用同一种类型，A/B 独立；无逐槽混合类型 |
| `in_hif4_e1_a`, `in_hif4_e1_b` | 入 | 各 4G | 每四个 HiF4 元素共享一个 1-bit e1 |
| `in_hif4_e2_a`, `in_hif4_e2_b` | 入 | 各 2G | 每八个 HiF4 元素共享一个 1-bit e2 |
| `in_c` | 入 | 32 | 与 A/B 同拍接收；S1–S4 仅保存 raw32，S5 解包 |
| `in_c_datatype` | 入 | c_type_bits，当前 1 | FP32 或 INT32，与 A/B 运算类别匹配 |
| `in_last` | 入 | 1 | 附属于 A 的请求控制；A valid 后未握手期间保持；不控制 DP 接收能力 |
| `out_valid` | 出 | 1 | 本沿前的结果有效；无 out_ready |
| `out_d` | 出 | 32 | FP32 编码或 INT32 补码 |
| `out_d_datatype` | 出 | c_type_bits，当前 1 | 与该笔结果同行；FP32/INT32，等于该笔合法输入的 c_datatype |
| `out_last` | 出 | 1 | 与该笔结果对应的 in_last；仅 out_valid 时有效 |

不再提供重复的全局 `in_mode` 或批次配置口。内部 `op_format` 由合法 datatype 元组派生。当前固定 RNE，无运行时 RM 端口；没有独立 scale ready/valid、跨请求累加控制或异常输出端口。integer overflow 在验证 trace 记录。

## 具名 datatype 与编码

以下为 v1.2 的新接口编码，不沿用旧 Scala 枚举数值。具名常量及编码表将由统一配置/参数定义提供给三实现与 TB；位宽由枚举最大编码推导，禁止各模块自写数值。保留码和未实现格式不作为合法输入。

| data datatype | 4-bit 编码 | lane 类别 |
| --- | --- | --- |
| TF32 | 0000 | T1 |
| FP16 | 0001 | H2 |
| BF16 | 0010 | H2 |
| MXFP8_E4M3 | 0011 | Q4 |
| MXFP8_E5M2 | 0100 | Q4 |
| MXFP6_E3M2 | 0101 | Q4 |
| MXFP6_E2M3 | 0110 | Q4 |
| MXFP4 | 0111 | E8 |
| NVFP4 | 1000 | E8 |
| HIF4 | 1001 | E8 |
| INT8 | 1010 | Q 并行度，整数语义 |
| 保留 | 1011..1111 | 非法 |

C/D 类型 FP32=0、INT32=1。scale 类型 NONE=00、E8M0=01、E4M3=10、E6M2=11；NONE 表示无 scale 路径，解码为内部单位 scale。扩展枚举需要版本化，不因某配置禁用一个格式而改变其端口编码。

| A datatype = B datatype | C / D | A、B scale datatype | 其他要求 |
| --- | --- | --- | --- |
| TF32 / FP16 / BF16 | FP32 | NONE | scale 数据、HiF4 元数据置零；不进入运算 |
| MXFP8 的两个子型 / MXFP6 的两个子型 | FP32 | E8M0 | 同侧 scale 按所属 32 项量化块广播 |
| MXFP4 | FP32 | E8M0 | 每相邻两个基本组 scale 相同 |
| NVFP4 | FP32 | E4M3 | 每组独立，合法 scale 非负 |
| HIF4 | FP32 | E6M2 | 同侧块 scale 广播，e1/e2 按组切分 |
| INT8 | INT32 | NONE | scale 数据、HiF4 元数据置零；整数路径 |

仅在 all_valid 时检查完整元组并报告其协议合法性；无效源的保留数据不触发请求错误。

A/B **数值**、scale **数值**始终可以不同；独立 datatype 字段不表示首版支持混格式相乘。A/B 不同类型、错误 C 类型、错误 scale 类型或保留枚举属于非法元组，不握手，TB 报告协议错误。数据内部的 NaN/Inf 等合法编码仍是有效请求，按数值规则输出，不可因特殊数拒绝接收。填充位、广播相等与 NV scale 非负等 payload 约束由源保证并由验证检查，不要求在 ready 组合路径复制全部数值检查器。

## 打包和分发

每侧连续低索引元素位于低位槽。`element[i] = payload[i*slot_bits +: slot_bits]`；TF32 取槽 [31] sign、[30:23] E、[22:13] F，[12:0]=0；MXFP6 取 byte [7:2]，[1:0]=0。每个基本组取连续 64 位 A/B，再拆两个连续 32 位 lane；T 使用完整 lane，H/Q/E 分别解释为 2/4/8 项。

`scale[g]=scale_bus[g*8 +: 8]`；`e1[g,j]=e1_bus[g*4+j]`、`e2[g,j]=e2_bus[g*2+j]`。HiF4 每组 16 项中 e1[j] 覆盖项 4j..4j+3，e2[j] 覆盖项 8j..8j+7。组、lane、元素、scale 的索引方向一致。其他打包与短 K 广播规则见 [容量与 scale](layout-and-scales.md)。

## 原子握手与逐笔顺序

```text
all_valid = in_a_valid & in_b_valid & in_c_valid
accept_enable = !reset & datatype_tuple_legal
out_a_ready = out_b_ready = out_c_ready = accept_enable & all_valid
req_fire = accept_enable & all_valid
```

只在 req_fire 采样全部数据、各 datatype 和 last，无部分接收、无内部拼接队列。各源不能等 ready 才产生 valid；各自 valid 拉高后，直到共同握手都保持本侧 payload、datatype、scale/meta 稳定。A 侧还保持 last。上游协调器保证三路按同一请求顺序到达，DP 不通过 tag 重排错位请求。

每个合法请求可以与前一笔不同格式，即使前笔仍在流水中也可接收。输入缺一份只插入 bubble，所有已接收请求继续推进。last=1 后下一拍仍可接收任意合法格式；last 不关闭 ready，不产生额外输出，不触发 drain。

沿前观察：沿 n 接收，S1 于 n 更新，S8 于 n+7 更新，沿 n+8 更新前下游/TB 采样输出，L=8。连续请求按原顺序输出；reset 生效时 clear valid/last，取消在途，不保留跨复位结果。详见 [逐笔控制](control.md)。

## 内部模块端口与时刻

以下是语义端口名与参数宽度，后续映射到实际 Bundle/模块文件；没有创建对应源码。内部使用无背压的 Valid token，不把忽略 ready 的接口声明为可停顿 Decoupled。

| 边界 | 输入 / 输出 | 必须同行的字段 | 时刻 |
| --- | --- | --- | --- |
| 顶层 → 基本组 | in_a/in_b 各 64 bit、每侧 scale8/e1×4/e2×2、ctrl、valid | 当前请求格式、scale 类型、last | 同一顶层 req_fire；不另加一级输入寄存 |
| 基本组 → lane | 每侧 32 bit、该 lane e1×2/e2×1、ctrl、valid | 当前请求控制和分类 | S1 解包归 lane，两个 lane 同步 |
| lane → 组 MAX → lane | exp_candidates/active、group_max | 指数和当前请求的有效掩码 | S2 组合侧接口；候选不依赖返回 MAX，无反馈环 |
| lane → 基本组 | SOP 补码 W_lane、r、zero/special、ctrl、valid/last | 默认 W_lane=30，r=U9 | S4 同拍输出；本地 F 由本笔 ctrl 推导 |
| ~~基本组 → 顶层~~ | ~~negative、magnitude[M_group]、anchor_top、zero/special、ctrl、valid/last~~ | ~~默认 M_group=30、anchor_top=S10~~ | ~~S5 所有字段同拍注册；不采用旧 anchor 早一拍的接口~~ |
| ~~基本组 → 顶层~~ | ~~negative、magnitude[M_group]、anchor_top、zero/special、ctrl、valid/last~~ | ~~默认 M30；浮点 S1I1F29、非零最高位1，anchor_top=e 为 signed10；INT 保持结构落位~~ | ~~L8 的 S5 同拍注册；备用 L9 对应 S6~~ |
| 基本组 → 顶层 | negative、magnitude_raw[M_group]、anchor_raw、leading_zero_count、zero/special、ctrl、valid/last | 默认M30、anchor_raw signed10、z unsigned5；浮点原幅值F按模式，未左移；INT z/anchor=0 | L8 S5同拍注册；备用L9为新增S6出口 |
| ~~C 支路 → 顶层~~ | ~~固定 sign+M32、anchor_top=S10、class、ctrl、valid~~ | ~~FP32 M24 低补 8 零，F31/A=alpha；INT32 M32/F0、浮点 anchor 置零；S5 解包~~ | ~~与本笔全部 S5 组 token 同拍~~ |
| ~~C 支路 → 顶层~~ | ~~固定 sign+M32、anchor_top、class、ctrl、valid~~ | ~~FP32 规格化 M24 后补8零、F31/e_c；INT32 M32/F0、anchor=0~~ | ~~与本笔所有规格化组 token 同拍；C 解包仍在 S5~~ |
| C 支路 → 顶层 | 固定sign+M32、anchor_raw、leading_zero_count、class、ctrl、valid | FP32 M24低补8零、F31，原有效无偏anchor及z_c；不动态左移；INT32 M32/F0、z/anchor=0 | S5解包，与组token同拍 |
| S6 → S7 | N 个 TC 对齐叶、A_common、ctrl、special、valid/last | 默认 N=5、叶 W40；INT 分支仅结构低零 | 一组叶对应同一请求，不逐源握手 |
| S7 → S8 | TC 总 SOP、A_common、ctrl、special、valid/last | 默认 W43；完整自然增长 | S8 按本笔输出类型处理 |

C 的 M32 取 FP32 significand 与 INT32 magnitude 所需宽度的最大值，补零数/小数位由格式参数推导；无效分类字段安全置零。

~~字段 `anchor_top` 表示最高幅值容器位权重，值公式为 `(-1)^negative*magnitude*2^(anchor_top-(M_group-1))`。SOP/anchor 各级格式及范围见 [S1–S8 出口表](stage-formats.md)。ctrl 可以共用一路逐级寄存后广播给同拍组/算术块；必须与数据阶段匹配，不能直接广播当前顶层 datatype 给所有级。~~

**v1.3：** 组字段改称anchor_raw，其值仍是原幅值容器最高位权重，value=sign×magnitude_raw×2^(anchor_raw-(M-1))；另外传z，e=anchor_raw-z供MAX。默认z有5位，zero/special另传；只给e而保留未左移幅值是错误接口。ctrl必须同行。

## 历史代码参考与新版差异

| 历史出处 | 可参考的设计 | 新版合同 |
| --- | --- | --- |
| [Interfaces.scala](../../../hw/legacy/chisel_src/Utils/Interfaces.scala) | A/B 各自 data_type、sf_type、scale/e1/e2 及 C 类型 | 新端口逐笔携带，首版同格式矩阵明确；固定 RNE 不复制旧 RM/out_type |
| [PE_HQE.scala](../../../hw/legacy/chisel_src/pe/PE_HQE/PE_HQE.scala)、[PEWiring](../../../hw/legacy/chisel_src/Utils/PEWiring.scala) | 组实例分发、合法格式检查、定点整数位对 anchor 修正 | 新增 C 内部合并；无稳定批次 in_cfg 依赖 |
| [PEGroup_HQE.scala](../../../hw/legacy/chisel_src/pe/PE_HQE/PEGroup_HQE.scala) | 分组 scale、零组屏蔽、紧凑 scale 乘法 | 组 S5 sign/magnitude 与 anchor 同拍，层级/项数按新版参数 |
| [SubPE_HQE.scala](../../../hw/legacy/chisel_src/pe/PE_HQE/SubPE_HQE.scala) | 小乘法器输入 mux、逐级 type 寄存 | 新 T1H2Q4E8 的产品/移位数量及 T/INT8 支持另按新合同 |
| [PEInterfaces.scala](../../../hw/legacy/chisel_src/Utils/PEInterfaces.scala) | sign/magnitude/anchor/zero/special 输出记录 | 仅用于内部 S5 token；新版顶层输出最终 FP32/INT32 |

旧 anchor/data 不同拍、旧输出 F、旧 11/18 级、混配能力和旧枚举均不自动继承。功能块边界与面积/功耗归属见 [统计合同](resource-accounting.md)。

## v1.1 接口与会话合同（已替代）

以下旧定义保留删除线；自 v1.2 起以本文前面的逐请求合同为准。

~~# DP 接口、输出与握手~~

~~状态：A/B/C 原子接收、无输出背压、会话模式固定、保留输入/输出 last、全局统一复位及浮点 FP32 C/D 已确认。精确握手表达式是下列候选合同；RM、INT8 C/D 编码和 scale/metadata 字段仍需闭合。~~

~~**v1.1 当前定义：** 原子握手表达式仍为候选；浮点 RNE、INT32 C/D 与回绕、scale 编码已明确；剩余数值边界及参数合法性继续完善。~~

~~## 计算边界与输出~~

~~每个有效请求携带完整配置 K 的 A、B、C 及适用 scale/metadata。浮点 DP 在内部完成缩放点积、部分和归约、与 FP32 C 对齐相加及 FP32 输出转换，数学目标为 `D = round_fp32(C + scaled_dot(A,B))`。有限位宽的实际计算顺序按逐级数值合同定义；该数学式本身不承诺无限精度点积只舍入一次。A/B scale 只作用于点积，不缩放 C。~~

~~DP 使用本笔携带的 C，不区分初始加数或前序结果，不自行反馈 D，也不维护跨请求 accumulator。C 的取数、指令级依赖及 C→D RAW 由上层保证，不再作为 DP 数值或控制合同的未决项。~~

~~所有浮点模式输出 FP32，内部 25/35/约 37 位保留目标另行定义。每笔接收对应一个结果；包括 NaN/Inf 在内的特殊结果保持同一模式的固定延迟，详见 [特殊值](special-values.md)。INT8 仍执行整数乘积规约及加 C；若采用纯整数 C/D 可跳过浮点对齐、归一化和舍入，其 C/D 编码和溢出规则待定。~~

~~**v1.1 当前定义：** INT8 采用 signed INT8×INT8+INT32 C，输出 INT32。首版与浮点共用八级寄存边界，S8 输出低 32 位回绕；溢出条件记录到验证 trace，不新增异常端口。~~

~~## 端口合同~~

| ~~信号~~ | ~~方向~~ | ~~合同~~ |
| --- | --- | --- |
| ~~`clock` / `reset`~~ | ~~入~~ | ~~所有 DP 子模块共用全局复位；同步方式/有效极性见控制文档~~ |
| ~~`in_a_valid`, `in_b_valid`, `in_c_valid`~~ | ~~入~~ | ~~源侧有效；scale/metadata 与所属 A/B payload 同步有效~~ |
| ~~`out_a_ready`, `out_b_ready`, `out_c_ready`~~ | ~~出~~ | ~~原子接收候选采用三路同拍握手，见下式~~ |
| ~~`in_mode`~~ | ~~入~~ | ~~首请求锁存本会话模式，后续请求保持同一模式；配置方式候选见控制文档~~ |
| ~~`in_a`, `in_b`~~ | ~~入~~ | ~~紧密打包，外部布局见 [容量合同](layout-and-scales.md)，内部固定字段见 [解包](unpack.md)~~ |
| ~~`in_scale_a`, `in_scale_b`~~ | ~~入~~ | ~~每 16 E 元素一槽；字段编码待定~~ |
| ~~`in_scale_a`, `in_scale_b`~~ | ~~入~~ | ~~每 16 E 元素一槽，八位 E8M0/E4M3/E6M2，内部统一 E8M3~~ |
| ~~`in_hif4_e1_a/b`, `in_hif4_e2_a/b`~~ | ~~入~~ | ~~每 16 E 元素含 4 个 1-bit e1 和 2 个 1-bit e2，按每 4/8 项共享~~ |
| ~~`in_c`~~ | ~~入~~ | ~~每请求一个 FP32 加数；INT8 下的位解释待定~~ |
| ~~`in_c`~~ | ~~入~~ | ~~浮点会话为 FP32；INT8 会话相同 32 位端口按二补码 INT32 解释~~ |
| ~~`in_last`~~ | ~~入~~ | ~~必须保留；本会话最后一笔请求，与该笔原子输入绑定~~ |
| ~~`out_valid`~~ | ~~出~~ | ~~结果有效，无 `out_ready`；下游保证接收~~ |
| ~~`out_d`~~ | ~~出~~ | ~~FP32 D；INT8 下的位解释待定~~ |
| ~~`out_d`~~ | ~~出~~ | ~~浮点会话为 FP32、仅 RNE；INT8 会话为二补码 INT32 回绕结果~~ |
| ~~`out_last`~~ | ~~出~~ | ~~输入 last 的对应输出标记；仅在 `out_valid=1` 时有效~~ |

~~目前不新增异常状态端口。异常条件与结果值先在数值合同中定义；是否输出逐请求 IEEE 异常 flags 另行决定。~~

~~## 原子握手候选~~

> ~~`all_valid = in_a_valid & in_b_valid & in_c_valid`~~
> ~~`accept_enable = 非复位 & 状态允许接收 & mode 合法且符合会话约束`~~
> ~~`out_a_ready = out_b_ready = out_c_ready = accept_enable & all_valid`~~
> ~~`req_fire = accept_enable & all_valid`~~

~~该候选中 ready 只在三份操作数同时可接收时拉高，每个源按自己的 valid/ready 观察到的 transfer 都等于 `req_fire`，不会出现部分接收。源不能等待 ready 才产生 valid；valid 拉高而未握手时，源保持 payload（含 scale/metadata、mode、last）稳定。scale/meta 随 A/B 有效，无独立握手或独立队列。~~

~~输入不齐形成 bubble；已接收请求仍推进，不因取数停顿延长延迟。输出固定延迟且无背压，DP-Group/测试环境必须在每次 `out_valid` 时接收。~~

~~## 模式固定与 last~~

~~首个 `req_fire` 锁定模式，后续请求使用同一模式。`req_fire & in_last` 关闭本会话输入并进入排空；未经握手的 last 无效。只有 `out_valid & out_last` 出现、最后结果输出完成后，才能接受下一会话的新模式。~~

~~输入 bubble 或流水暂时为空都不结束会话；未提交 last 时继续保持模式。last 表达取数流的结束边界并随结果传递，不触发额外累加，也不改变本请求的 A×B+C 计算。~~

~~## v1.1：基本组内部接口~~

~~T2H4Q8E16 的 S5 接口采用独立 negative、无符号 magnitude、anchor/F、zero/special、valid/last。S6 对幅值向零截断后恢复补码，S7 才规约所有组与 C。位宽及字段数量由 [数值合同](numeric-layout.md) 和构建参数派生，内部接口不改变外部原子握手与模式会话规则。~~


## 历史修订对照

以下为本次版本化时恢复的历史草案对照；删除线内容已被替代，不作为当前实现依据。较早内容尚无正式版本号，来源按真实提交或用户确认记录，不追认其为已批准合同。

- **last**：~~标记数据流中本次会话/帧的末项候选；是否必需待确认。~~ → **当前：**in_last 必须保留，与原子请求绑定，并传递为 out_last。（来源：dba8ecf → 42350c5，用户确认）

- **C 来源**：~~C 是每个独立点积请求的初始加数，还是流中逐项累加的前序结果，仍待确认。~~ → **当前：**DP 只使用本笔 C 计算缩放点积加 C；取数与依赖由指令层保证。（来源：dba8ecf → 42350c5，旧待决问题摘要）

## v1.3：计数 token 与固定延迟

S5输出原幅值/anchor_raw/z，S6完成合并移位；最小字段不同时存三套A_raw/e/z。外部端口不变，初版L8；备用post_scale_norm_extra_stage=1时全部模式L9，静态配置不可逐请求变化。所有源及控制同步。S6/S7 的公共anchor字段A_common是实际指数E_max（数值同义，建议trace使用E_max区分raw）。

## 本轮未提交草案对照：v1.3：规格化出口及备用固定延迟

~~## v1.3：规格化出口及备用固定延迟~~

~~浮点组/C 的 anchor_top 仍表示最高幅值位权重，现在非零 magnitude 最高位恒1，因此也是真实无偏指数；value=sign×magnitude×2^(anchor_top-(M-1))。INT 分支坐标不变。外部端口不变；首选 L8，备用 post_scale_norm_extra_stage=1 时所有格式固定 L9，内部全局对齐/总树/输出阶段顺延。禁止依据当前 datatype 动态切换此构建参数。~~

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| 未编号（追溯） | 2026-11-04T17:02:03+08:00 | 历史记录 | 细化分组共享、K 参数化、scale/metadata、接口与八周期候选。 | [dba8ecf](https://github.com/Futuresxy/DP-Puzzel/commit/dba8ecf) |
| 未编号（追溯） | 2026-11-04T17:28:50+08:00 | 历史记录 | 明确固定解包、C/last 边界、全局复位及特殊值规则。 | [42350c5](https://github.com/Futuresxy/DP-Puzzel/commit/42350c5) |
| v1.0 | 2026-11-04 17:36:11 +08:00 | 文档版本基线 | 建立页首元信息、代码映射状态及修订时间线；保留已有正文，恢复适用的旧稿删除线对照。架构及原有确认状态不变。 | 用户文档维护要求；[版本规则](../document-control.md) |
| v1.1 | 2026-11-04 19:12:59 +08:00 | 架构修订 | 补充 v1.1 相关资源、数值或验证合同。 | 用户架构图与补充；[总时间线](../CHANGELOG.md) |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 架构修订 | 重写顶层端口/编码/合法矩阵和内部接口；独立 datatype、无会话锁定、结果类型、历史 PE_HQE 对照。 | 用户本轮要求及确认；[总时间线](../CHANGELOG.md) |
| v1.3 | 2026-11-04 21:03:38 +08:00 | 架构修订 | 按用户最终选择，S5 scale后LZD仅计数、S6一次双向移位；同步数值/接口/资源/备用周期，保留对照。 | 用户最终双向移位选择；[总时间线](../CHANGELOG.md) |
