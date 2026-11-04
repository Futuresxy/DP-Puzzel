> 功能：定义 DP 顶层和模块接口；范围：端口/编码、原子握手、逐笔 datatype、内部 token；版本：v1.4.1；修改时间：2026-11-04 22:08:44 +08:00；对应代码：[CModel include/dp/model.hpp](../../cmodel/include/dp/model.hpp)；Chisel/手写 Verilog 模块尚未实现。

# DP 顶层与模块接口定义

状态：当前 H16Q32E64（T8）及 K4/K8 变体的接口合同。用户确认 A/B 各自携带 datatype、首版仅同格式；C 在 S5 按 FP32/INT32 解包；每笔控制随流水推进，取消 DP 内会话锁定。原子 ready 及逐请求协议已在 CModel 验证；RTL 电气复位方式仍待实现时冻结。

## 1. 运算和模块边界

浮点每笔计算有限位宽路径规定的 `scaled_dot(A,B)+C`，S8 以 RNE 输出 FP32；INT8 每笔计算有符号点积加 INT32 C，内部精确保留，S8 取低 32 位回绕。A/B scale 不作用于 C。DP 不持有跨请求 accumulator，不处理 C 的指令依赖。

三层为 T1H2Q4E8 → T2H4Q8E16 → H16Q32E64；主配置 k_fp16=16、G=4 个基本组。所有模式均 L=8，目标 II=1，无输出 ready。相邻请求可使用不同合法格式，last 仅是随请求传递的上层流标记。

## 2. 构建期端口尺寸

令 `G=k_fp16/base_group_fp16_k`、基本组基准为 4、每组两个 32 位逻辑 lane：

| 字段规模 | 派生式 | K4 / K8 / K16 |
| --- | --- | --- |
| 每侧 A/B payload | k_fp16 × FP16 容器位数 | 64 / 128 / 256 bit |
| 每侧 scale | G × scale_container_bits，后者为 8 | 8 / 16 / 32 bit |
| 每侧 HiF4 e1 | G × (E16/每 e1 覆盖 4 项) | 4 / 8 / 16 bit |
| 每侧 HiF4 e2 | G × (E16/每 e2 覆盖 8 项) | 2 / 4 / 8 bit |
| C / D | FP32 与 INT32 共用编码容器 | 32 / 32 / 32 bit |

总线是 elaboration 后固定宽度，运行时 datatype 只改变同一总线的解释。TF32=K/2 个 32 位槽、H=K 个 16 位槽、Q/INT8=2K 个 8 位槽、E=4K 个 4 位槽，均占 16K bit。

## 3. 顶层端口

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

## 4. 具名 datatype 与编码

以下为当前接口编码，不沿用旧 Scala 枚举数值。具名常量及编码表将由统一配置/参数定义提供给三实现与 TB；位宽由枚举最大编码推导，禁止各模块自写数值。保留码和未实现格式不作为合法输入。

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

## 5. 打包和分发

每侧连续低索引元素位于低位槽。`element[i] = payload[i*slot_bits +: slot_bits]`；TF32 取槽 [31] sign、[30:23] E、[22:13] F，[12:0]=0；MXFP6 取 byte [7:2]，[1:0]=0。每个基本组取连续 64 位 A/B，再拆两个连续 32 位 lane；T 使用完整 lane，H/Q/E 分别解释为 2/4/8 项。

`scale[g]=scale_bus[g*8 +: 8]`；`e1[g,j]=e1_bus[g*4+j]`、`e2[g,j]=e2_bus[g*2+j]`。HiF4 每组 16 项中 e1[j] 覆盖项 4j..4j+3，e2[j] 覆盖项 8j..8j+7。组、lane、元素、scale 的索引方向一致。其他打包与短 K 广播规则见 [容量与 scale](layout-and-scales.md)。

## 6. 原子握手与逐笔顺序

```text
all_valid = in_a_valid & in_b_valid & in_c_valid
accept_enable = !reset & datatype_tuple_legal
out_a_ready = out_b_ready = out_c_ready = accept_enable & all_valid
req_fire = accept_enable & all_valid
```

只在 req_fire 采样全部数据、各 datatype 和 last，无部分接收、无内部拼接队列。各源不能等 ready 才产生 valid；各自 valid 拉高后，直到共同握手都保持本侧 payload、datatype、scale/meta 稳定。A 侧还保持 last。上游协调器保证三路按同一请求顺序到达，DP 不通过 tag 重排错位请求。

每个合法请求可以与前一笔不同格式，即使前笔仍在流水中也可接收。输入缺一份只插入 bubble，所有已接收请求继续推进。last=1 后下一拍仍可接收任意合法格式；last 不关闭 ready，不产生额外输出，不触发 drain。

沿前观察：沿 n 接收，S1 于 n 更新，S8 于 n+7 更新，沿 n+8 更新前下游/TB 采样输出，L=8。连续请求按原顺序输出；reset 生效时 clear valid/last，取消在途，不保留跨复位结果。详见 [逐笔控制](control.md)。

## 7. 内部模块端口与时刻

以下为语义端口与参数宽度；CModel 观察点已映射，RTL Bundle/模块文件尚未建立。内部使用无背压的 Valid token，不把忽略 ready 的接口声明为可停顿 Decoupled。

| 边界 | 输入 / 输出 | 必须同行的字段 | 时刻 |
| --- | --- | --- | --- |
| 顶层 → 基本组 | in_a/in_b 各 64 bit、每侧 scale8/e1×4/e2×2、ctrl、valid | 当前请求格式、scale 类型、last | 同一顶层 req_fire；不另加一级输入寄存 |
| 基本组 → lane | 每侧 32 bit、该 lane e1×2/e2×1、ctrl、valid | 当前请求控制和分类 | S1 解包归 lane，两个 lane 同步 |
| lane → 组 MAX → lane | exp_candidates/active、group_max | 指数和当前请求的有效掩码 | S2 组合侧接口；候选不依赖返回 MAX，无反馈环 |
| lane → 基本组 | SOP 补码 W_lane、r、zero/special、ctrl、valid/last | 默认 W_lane=30，r=U9 | S4 同拍输出；本地 F 由本笔 ctrl 推导 |
| 基本组 → 顶层 | negative、magnitude_raw[M_group]、anchor_raw、leading_zero_count、zero/special、ctrl、valid/last | 默认 M30、anchor_raw signed10、z unsigned5；浮点原幅值 F 按模式，未左移；INT z/anchor=0 | L8 S5 同拍注册；备用 L9 为新增 S6 出口 |
| C 支路 → 顶层 | 固定 sign+M32、anchor_raw、leading_zero_count、class、ctrl、valid | FP32 M24 低补 8 零、F31，原有效无偏 anchor 及 z_c；不动态左移；INT32 M32/F0、z/anchor=0 | S5 解包，与组 token 同拍 |
| S6 → S7 | N 个 TC 对齐叶、A_common、ctrl、special、valid/last | 默认 N=5、叶 W40；INT 分支仅结构低零 | 一组叶对应同一请求，不逐源握手 |
| S7 → S8 | TC 总 SOP、A_common、ctrl、special、valid/last | 默认 W43；完整自然增长 | S8 按本笔输出类型处理 |

C 的 M32 取 FP32 significand 与 INT32 magnitude 所需宽度的最大值，补零数/小数位由格式参数推导；无效分类字段安全置零。

组字段改称 anchor_raw，其值仍是原幅值容器最高位权重，value=sign×magnitude_raw×2^(anchor_raw-(M-1))；另外传 z，e=anchor_raw-z 供 MAX。默认 z 有 5 位，zero/special 另传；只给 e 而保留未左移幅值是错误接口。ctrl 必须同行。

## 8. 计数 token 与固定延迟

S5 输出原幅值/anchor_raw/z，S6 完成合并移位；最小字段不同时存三套 A_raw/e/z。外部端口不变，初版 L8；备用 post_scale_norm_extra_stage=1 时全部模式 L9，静态配置不可逐请求变化。所有源及控制同步。S6/S7 的公共 anchor 字段 A_common 是实际指数 E_max（数值同义，建议 trace 使用 E_max 区分 raw）。
