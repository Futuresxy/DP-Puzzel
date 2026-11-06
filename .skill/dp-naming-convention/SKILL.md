---
name: dp-naming-convention
description: >
  DP-Puzzel 文件、目录、模块、实例、接口、内部变量和文档命名规范。
  新增或重命名 DP 设计文件、模块、端口、互联信号、流水变量、参数、函数或接口文档，
  以及审查 e/f/a 等含义不明的缩写时使用。与 dp-rtl-code-style 配合，
  保留现有 src/test/hw 布局和冻结 SV 范围，不自动批量改名或改变接口协议。
---

# DP 全局命名规范

以用户指定的 `sn-naming-convention` 为基础，保留命名维度表、模块层级表、新增模块清单、驱动方/接收方互联规则、各类接口示例、CSV 文档格式和审查清单，再补充 DP 数值和流水变量规则。来源及移植对应见 [移植与现有命名审查](references/adaptation-and-audit.md)。

先读根目录 `AGENTS.md`、相关 spec 和 [dp-rtl-code-style](../dp-rtl-code-style/SKILL.md)。本 skill 管命名含义，code-style 管声明、组合/时序结构和 DFF 选型。新增/修改命名须遵守本规范；现有接口迁移须连同引用和验证一起完成。现用 CModel/Verilog 的 v1.6 迁移见 test/results/dp-style-v1.6.md；新增修改继续按本规范同步引用与验证。

## 一、`dp_` 前缀原则与文件组织

### 1.1 命名维度对照表

DP 设计模块、RTL 文件、项目共享宏采用统一前缀；不要为前缀规则搬动既有目录。固定工具入口、源清单和历史记录保留其合同名称。

| 维度 | 规范 | 示例/当前适配 |
| --- | --- | --- |
| 根目录 | 按职责保留，不加 dp_ | `src/` 开发、`test/` 验证、`hw/` 综合/功耗 |
| RTL 目录 | 按功能层级 | `src/verilog/lane/`、`group/`、`top/`、`unpack/`、`arithmetic/` |
| RTL 文件名 | `dp_{function}[_{variant}].v` | `dp_lane.v`、`dp_lane_e.v`、`dp_scale_multiply.v` |
| RTL 模块名 | 与文件主名完全一致 | `dp_lane_e`；每文件一个 module |
| DFF 库模块 | 保留类型后缀，前缀 dp_lib_ | `dp_lib_DFFRE`，是小写模块规则的明确例外 |
| 头文件 | `dp_{purpose}.vh`，宏 `DP_...` | `dp_defs.vh`、`dp_functions.vh` |
| RTL TB | `dp_{scope}_tb[_{purpose}].v/.sv` | 现有 `test/rtl_tb/dp_tb.v` 保持；新增可用 `dp_lane_e_tb.v` |
| TB 支持文件 | `dp_{scope}_{role}.vh/.v` | 现有 `dp_tb_e_trace.vh`；driver/monitor/checker 明确角色 |
| 验证目录 | 沿用 test 的职责分工 | `test/rtl_tb/`、`test/reference/`、`test/results/` |
| 编译清单 | 保留现有稳定入口 | `src/verilog/files.f`、`files_e.f`，不改为 SN 的 flist 树 |
| 构建/运行入口 | 按职责命名，保留当前 CLI | `test/run_verilog.py --frontend e`；不引入不存在的 build.py target |
| CModel 文件 | 功能可读，结合 dp namespace | 现有 `unpack.cpp`、`top/backend.cpp`；新增避免单字母文件名 |
| CModel 类型/函数 | 遵循所在语言既有风格，词根含义与 spec/RTL 对齐 | 不把 Verilog 的 dp_ 和 `_q` 机械套到所有 C++ 对象 |
| Chisel | 遵从 AGENTS.md 的 Scala 规则 | 类/Bundle UpperCamelCase，硬件信号 lower_snake_case；默认 clock/reset 不在此轮改名 |
| 配置 | 用前端/容量/参数含义 | 现有 `src/configs/dp/e64.json`；不给临时配置取 final/new/test2 |
| 微架构文档 | 保留 lane/group/dptop 层级 | 现有 `src/spec/dp/lane/dp_lane_E.md` 是已存在文件，不因大小写规则自动改名 |
| 新接口 CSV | `dp_{scope}_interface.csv` | 如后续创建 `dp_lane_e_interface.csv`；不按命名任务自动创建一套 CSV |
| 测试计划 | `dp_{scope}_testplan.md` | 存在需要时创建，遵守目标目录规范 |
| 覆盖/评审报告 | `{scope}_{purpose}.md` | `dp_lane_e_coverage.md`、`dp_group_naming_review.md` |
| 测试/EDA run 与快照 | 使用现有工具生成的 ID | `DP_verilog_<fingerprint>`、现有 run ID，不改为可变的 latest/final |

容量是参数时不编码进通用模块名：`dp_top_e` 不改成 `dp_e64_k16_l28_g40`。测试配置和报告负责记录实际容量。标准格式名 FP16/FP32、MXFP4/NVFP4/HiF4 在标识符中写 `fp16/fp32/mxfp4/nvfp4/hif4`，文档保留标准拼写。

### 1.2 DP 层级与短名对照表

| 功能边界 | 稳定模块/路径 | 互联短名 | 说明 |
| --- | --- | --- | --- |
| 单 DP | `dp_top`、`dp_top_e` | `top` | 当前单 DP 顶层，不表示计算阵列 |
| 基本算术 group | `dp_group`、`dp_group_e` | `group` | DP 内两 lane 合并，区别于阵列层 DP-Group |
| lane | `dp_lane`、`dp_lane_e` | `lane` | 当前前端计算层级 |
| 元素/操作数解包 | `dp_operand_unpack`、`dp_lane_unpack`、`dp_lane_unpack_e` | `unpack` | 同域多份时用 `unpack_a`、`unpack_b` 区分 |
| 尾数乘法 | `dp_mantissa_bank`、`dp_mul_unsigned` | `mantissa_mul` | 不用意义不明的 `m` |
| 指数 MAX | `dp_max_tree` 的对应实例 | `exponent_max` | 模块可通用，实例短名体现具体用途 |
| scale 乘法 | `dp_scale_multiply` | `scale_mul` | 与输入尾数乘法区分 |
| 全局对齐 | `dp_global_align` | `global_align` | group token 与 C 对齐 |
| 最终规约 | `dp_sum_tree` 的对应实例 | `final_sum` | 不把所有树都叫 tree0 |
| FP32 输出转换 | `dp_fp32_round` | `fp32_round` | 规格含归一化/舍入/打包 |

短名按**本层实例角色**定义，并在端口/互联表说明映射。同类型多个实例使用 `lane0/lane1` 等，或参数化数组及 `lane_index`；不能仅写 `lane_lane_*` 而无法区分端点。

`_e` 仅在已定义的前端类型名称中表示 E 专用族，如 `dp_lane_e`、`files_e.f`。它不表示 exponent，更不能成为允许局部变量裸写 `e` 的理由。HiF4 的 `e1/e2` 是规范字段名，新增本地信号写 `hif4_e1` / `hif4_e2` 或结合用途，既有端口迁移另行核对。

### 1.3 新增模块检查清单

```text
□ 在正确的 lane/group/top/unpack/arithmetic/common 目录，不新造一套 box 目录
□ 文件名 = module 名 + .v，具有 dp_ 前缀和可读功能名
□ 变体名仅表达稳定实现区别，不把可变参数硬编码进模块名
□ 普通实例 u_<function>；DFF 实例 ff_<source_stage>_<dest_stage>_<payload>
□ generate 使用 g_<function>，循环索引用 <role>_index
□ 明确主/E 哪些 files.f 需要加入该模块，不靠 glob 混入同名实现
□ test/rtl_tb 和必要验证文档命名对应模块功能
□ spec 映射、源清单、TB 层级路径和导出引用同步
□ 未修改冻结 SV、旧快照、旧报告及用户无关改动
```

## 二、接口信号命名规范

### 2.1 核心原则与作用域

**父模块内连接两个子模块的互联线**使用 `{driver}_{receiver}_{function}`，三个部分分别说明驱动方、接收方和传递的含义。端点使用上表定义的短名，不重复 `dp_`。

可复用子模块自己的端口继续使用 `in_{function}` / `out_{function}`；时钟 `clock`、复位 `rst_n` 是例外。模块内部的局部运算变量只写功能和必要阶段，不强加端点前缀。顶层输入操作数 A/B/C 是已定义的数学角色，保留 `in_a/in_b/in_c`，不是禁止的无上下文局部 a/b/c。

```verilog
// 示意连接片段，实例名称表达功能，互联线表达方向和内容。
wire signed [LANE_SUM_W-1:0] lane_group_sum_s4;

dp_lane u_lane (
  // 其余端口按该模块接口连接。
  .out_sop(lane_group_sum_s4)
);
```

示意中的 `lane_group_sum_s4` 表示 lane 输出供 group 使用的 S4 和；不要求为改名再增加 DFF。完整 RTL 必须连接完整端口，不能照抄省略端口的片段作为完整实例。

### 2.2 信号名结构模板

```text
互联线：{driver}_{receiver}_{function}[_{operand_or_slot}][_s{stage}][_{role}]
端口：  in_{function} / out_{function}
局部值：{function}[_{operand_or_slot}][_s{stage}][_{role}]
role：  d = 下一寄存输入；q = 寄存输出；en = 更新使能；n = 低有效
```

- 全小写、下划线分词；时钟/复位和类型名例外已列明。
- 词根在全项目一致：使用 `valid/ready`，不混用 vld/rdy/v/r 表示同一类信号。
- 多槽采用描述性索引/数组，必须展开的标量使用 `_0/_1`；不要把 `s1`（流水第 1 级）与槽位 `_1` 混淆。
- 寄存状态以 `_q` 结束，如 `group_magnitude_s5_q`；组合下一状态以 `_d` 结束，如 `group_magnitude_s5_d`。前级与后级不能沿用同一个模糊名字。
- `_s3_d` 表示将写入 S3 的值，`_s3_q` 表示 S3 保存后的值。跨模块线可仅标输出阶段 `_s4`；若使用 `_q`，必须确实来自该边界寄存器。组合 MAX 输出不能为了统一样式伪装成寄存结果。
- 驱动/接收前缀用于模块边界，避免模块内部所有名字都重复一长串层级。

### 2.3 常见接口类型

以下是命名示例，不代表新增接口或已经实施的改名。S4/S5 的例子以多精度前端为背景；E 前端的 lane/group 流水归属按对应 spec 标注，不机械复制阶段号。

#### 2.3.1 单 bit 控制信号

| 名称 | 方向 | 含义 |
| --- | --- | --- |
| `top_group_valid` | top → group | 合法请求的组内启动有效 |
| `group_lane_valid` | group → lane | 当前 lane 输入有效 |
| `lane_group_valid_s4` | lane → group | S4 lane 输出有效 |
| `group_top_valid_s5` | group → top | S5 group 输出有效 |

#### 2.3.2 多 bit 数据和数值字段

| 名称 | 含义/位宽来源 |
| --- | --- |
| `top_group_operand_a` | 分发给 group 的 A，宽度由容量/布局推导 |
| `group_lane_operand_b` | 分发给 lane 的 B，不称 b0 |
| `lane_group_sum_s4` | lane 有符号规约结果，宽度由局部窗口和项数推导 |
| `group_top_magnitude_s5` | group S5 幅值，不包含独立 sign |
| `group_top_anchor_s5` | 幅值最高物理位的指数坐标，不等于 encoded exponent |
| `group_top_sign_s5` | 对应 magnitude 的独立符号 |

#### 2.3.3 Valid/Ready 握手对

```text
valid: {driver}_{receiver}_valid
ready: {receiver}_{driver}_ready
```

ready 的驱动方在前，因为它从接收者返回发送者。若外部 source 与 DP 的互联后续使用方向名，可称 `source_top_valid` / `top_source_ready`；子模块端口仍按其本地方向命名。

**当前 DP lane/group 内无独立 ready/stall 握手，顶层输入原子接收，无输出背压。命名规范不授权增加 ready、停顿或 FIFO。**

#### 2.3.4 反压/停顿信号

若未来某接口合同定义反压，采用 `{receiver}_{driver}_stall`，full 信号按实际产生方命名。`stall` 必须能回答“谁要求谁停”；不能仅凭接收端名称决定前缀。目前单 DP 内部不新增此类信号。

#### 2.3.5 结果返回与广播

原规范的执行单元写回/唤醒命名在 DP 中对应结果传递：`fp32_round_top_result_bits`、未来上层的 `top_sink_result_valid`。功能词 result/datatype/last 分别表达语义；不得因为命名规则引入 OOO tag/唤醒机制或跨请求累加。

广播一条线给多个接收方时，使用已定义的接收组名，或在分支处分别命名；文档列出所有消费者，不能伪造唯一 receiver。

#### 2.3.6 多操作数、多 lane/group 端口

```text
{driver}_{receiver}_{operand_or_port}_{function}
```

| 名称 | 含义 |
| --- | --- |
| `top_group_a_scale_bits` | A 的 scale 编码数据 |
| `top_group_b_scale_bits` | B 的 scale 编码数据 |
| `group_lane0_operand_a` | group 到 lane0 的 A |
| `group_lane1_operand_a` | group 到 lane1 的 A |

参数化实现优先保留数组/generate 索引，注释其 group/lane/element 轴，不写死 lane0/lane1 扩展所有参数。原规范中的 CRF 读写口规则在本项目只作为多端口命名原则，不新增 CRF 模块。

#### 2.3.7 接口组命名

CSV 或接口表中的组名采用 `{driver}2{receiver}[_{purpose}]`：`lane2group`、`group2top`、`top2group_operand_a`。接口组标签中的数字 2 表方向；RTL 信号名仍用下划线，不混成 `group2top_valid`。

### 2.4 正确与错误示例

```text
❌ valid0                  跨模块线上看不出方向和所属数据
✅ lane_group_valid_s4     明确边界和阶段

❌ group_data              不知是输入编码、累加和还是输出 token
✅ group_top_magnitude_s5  明确内容、方向和阶段

❌ stall                   不知谁要求谁停
✅ sink_source_stall       仅在该接口确有反压合同时使用

❌ a                       局部运算中含义不明
✅ product_even            pair 的偶数项乘积
✅ in_a                    顶层已定义的操作数 A，允许保留
```

## 三、内部变量、函数和数值命名

### 3.1 禁止无含义缩写

功能变量、函数形参、局部中间量不得使用裸 `a/b/c/d/e/f/m/n/t/x/y`，或 `tmp/tmp1/data0/val/res` 等不能解释用途的名称。作用域短也不能把 exponent/fraction/product 缩成单字母。

允许的有限例外：

- 已有数学操作数端口 `in_a/in_b/in_c`、有定义的 DFF 端口 `in_d/out_q`、寄存后缀 `_d/_q`。
- 数值说明中的 S/I/F、K 等数学符号，标准精度族/格式名和 HiF4 e1/e2 字段；硬件变量仍用可读功能词。
- 已有通用算术模块参数 `N/W/A_W/B_W` 等是兼容接口，不能未经依赖核查整体改名；新接口优先 `INPUT_COUNT/VALUE_W/OPERAND_A_W/OPERAND_B_W` 等。
- 纯数学推导可写局部符号，但需要在邻近注释映射到代码变量。不要借此允许硬件中间值继续叫 e/f。

循环/generate 新代码使用 `group_index/lane_index/element_index/pair_index/bit_index`，嵌套循环各有角色。不要为避免单字母而仅改成 index1/index2；不要将改名顺便变成循环展开或调度变化。

### 3.2 DP 术语词典

| 含义 | 推荐词根/例子 | 避免混淆 |
| --- | --- | --- |
| 原始浮点编码 | `operand_bits`、`scale_bits` | 不是已解码 magnitude |
| 编码指数域 | `exponent_field` | 带编码偏置，不能叫 unbiased_exponent |
| 去偏置的数学指数 | `unbiased_exponent` | 区别于 anchor 和指数域 |
| exponent 的编码位数 | `exponent_field_width` | 不是指数数值 |
| 编码 fraction 域 | `fraction_field` | 不含隐含位，不等于完整 significand |
| fraction 的编码位数 | `fraction_field_width` | 不是定点通路 fractional bits |
| 定点小数位数 | `fractional_bits`、`group_fractional_bits` | 对应 S/I/F 的 F |
| 解码后的有效数 | `significand`；已有 `mantissa` 保留定义 | 两种词不在同一新模块中随意混用 |
| 无符号绝对幅值 | `magnitude` | 符号另传，不叫 signed_magnitude 表达 TC |
| 有符号累加和 | `lane_sum`、`group_sum`、`signed_sum` | 不能用 magnitude 表示二补码 |
| 比例系数/scale 乘积 | `scale_coefficient`、`scaled_product` | 区分 scale 编码和解码系数 |
| 最高物理位坐标 | `anchor`、`group_anchor` | 不等于实际最高非零位指数 |
| 实际最高有效位指数 | `leading_exponent` | 由 anchor 与 leading-zero count 得出时写明关系 |
| 前导零个数 | `leading_zero_count` | 不用 l/z/leading 代表多种含义 |
| 对齐差值 | `alignment_delta`、`exponent_delta` | 明确减法方向和正负含义 |
| 移位量 | `left_shift_amount`、`right_shift_amount` | 双向量必须注释正负方向 |
| 最大树结果 | `left_max`、`right_max` | 不用 a/b |
| 最大树叶活动性 | `left_active`、`right_active` | active 不自动等于请求 valid |
| 舍入 | `guard_bit`、`sticky_bit`、`round_increment` | guard bit 不同于溢出增长位 |
| 特殊值状态 | `special_flags`、`is_nan`、`is_inf` | 不用 s 或 flag1 |

RTL `sum` 不自动命名为 `accumulator`：当前 DP 无跨请求累加状态。`valid` 表示请求/流水有效，`active` 表示参与数值规约等条件，`nonzero` 仅表示数值非零；不要互换名称掩盖不同合同。

### 3.3 从当前代码得到的具体例子

以下是经阅读实现后的改名建议，**本次未实施**；完整定位和解释见移植记录。

| 当前名字/位置 | 建议名字 | 理由 |
| --- | --- | --- |
| `dp_operand_unpack` 的 e | `exponent_field` | 从原始编码提取的指数域 |
| 同模块的 f | `fraction_field` | 未加隐含位的编码 fraction |
| eb / fb | `exponent_field_width` / `fraction_field_width` | 两者都是域宽度 |
| raw / n | `operand_bits` / `decoded_number` | 区分输入编码和输出数值 token |
| `dp_max_tree` 的 a / b | `left_max` / `right_max` | 左右子树输出 |
| 同模块的 va / vb | `left_active` / `right_active` | 相应子树活动性 |
| `dp_sum_tree` 的 a / b | `pair_left_value` / `pair_right_value` | 两个规约叶值 |
| `dp_lane_e` pair 的 a / b | `product_even` / `product_odd` | 相邻两个有符号乘积 |
| 格式函数形参 t | `datatype` | 运行时格式选择 |

函数名描述结果或判断：`decode_operand`、`compute_group_fractional_bits`、`is_supported_datatype`；不使用 do_calc/get_f/process1。这些是命名模式，现有函数重命名需同步调用方，不能推断已经存在这些 API。

### 3.4 文件和变体的歧义

单独 `e.cpp` 在已知目录可推断 E 前端，但脱离路径易读错；新增文件优先 `lane_e.cpp` / `group_e.cpp` 等含功能名的形式。现有 `lib/lane/e.cpp`、`lib/group/e.cpp` 列为后续可审查迁移项，本次不搬文件、不修改构建目标。`dp_top_e` 的已定义后缀则足够清晰，不需要机械替换成冗长名称。

## 四、接口文档与 CSV 命名规范

### 4.1 表头

保持原规范的接口文档维度。若任务需要 CSV，使用以下列；现有 Markdown 合同可以使用同等信息，不因本 skill 自动建立重复文档。

| 列名 | 含义 | 示例 |
| --- | --- | --- |
| 信号名 | 父层互联完整名 | `lane_group_sum_s4` |
| 方向 | 相对本行主体，O 输出、I 输入；必须说明主体 | `O`，以 lane 为主体 |
| 宽度 | 参数公式或位数 | `LANE_SUM_W` |
| 驱动模块 | 实例角色及 module | `u_lane:dp_lane` |
| 接收模块 | 实例角色及 module | `u_group:dp_group` |
| 接口组 | driver2receiver | `lane2group` |
| 描述 | 功能、signed/unsigned、阶段 | S4 二补码 lane 和 |

若记录嵌套的父子关系而非兄弟实例，在实例路径中体现真实层级。端口名与互联名不同，应增加驱动端口/接收端口列；不为了统一字符串把真实端口写错。源/目标在行中明确，方向列不能同时相对两边解释。

### 4.2 注释和分组

```csv
# 以下仅示意，以 lane 为主体，宽度为参数公式。
信号名,方向,宽度,驱动模块,接收模块,接口组,描述
lane_group_sum_s4,O,LANE_SUM_W,dp_lane,dp_group,lane2group,S4 有符号规约和
```

CSV 的 `#` 注释是文档约定，解析脚本必须显式跳过，否则不要混用注释与纯 CSV 数据。规格格式/修订号遵循 `src/spec/document-control.md`，不沿用原项目固定的 Version0 编号。

### 4.3 文件名

| 类型 | 命名示例 |
| --- | --- |
| 顶层端口 | `dp_top_interface.csv`、`dp_top_e_interface.csv` |
| group/lane 互联 | `dp_group_interconnect.csv` |
| 单模块接口 | `dp_lane_e_interface.csv` |

现有文件名不因本规范自动迁移；新建 spec Markdown 仍须填写规定的首行版本/时间/代码映射。

## 五、审查检查清单

### 5.1 文件、目录、模块

1. RTL 文件与 module 同名，dp_ 前缀正确，DFF 类型后缀例外明确。
2. 目录沿用 src/test/hw 职责，不增加另一套 rtl/verification 层级。
3. 新增文件/函数不使用无含义单字母、tmp、final2 等名字。
4. 变体、参数和精度族区别明确，未将参数化单元命名成固定配置。
5. TB/清单/构建入口与模块相符，未破坏现有稳定工具路径。
6. 文档名称可识别模块与功能，接口表有清晰来源与版本。

### 5.2 接口、变量、实例

1. 父层互联写明驱动方/接收方/功能，端点映射可追溯。
2. 模块端口使用 in_/out_；本地变量无需重复外部端点。
3. ready/stall 按实际驱动方向命名；未给无握手通路虚构握手。
4. 多 group/lane/element 轴、槽位号、流水阶段不混淆。
5. DFF 实例明确保存边界，d/q/en/n 后缀与真实行为一致。
6. e/f/a 等已根据使用语义展开；指数域、指数值、域宽和小数位数不混淆。
7. valid/active/nonzero、signed sum/magnitude、mantissa/fraction 含义准确。
8. 循环索引、函数及局部变量使用功能词，兼容接口例外有明确依据。
9. 同功能词在 spec/CModel/RTL/TB 对齐，语言风格分别遵守。

审查表逐项标明“通过/不通过/N/A/未检查”，失败给出文件和行号、含义及建议；不要靠搜索单字母自动重命名。详细变量映射放审查结果或变更说明，避免仅输出“风格已统一”。

## 六、重命名实施边界

- 命名讨论/skill 更新仅更新规则，不默认授权全仓改名。接到实际迁移任务后先建立旧名→新名→作用域→语义映射，保护用户未提交改动。
- 局部名可按模块迁移；端口/module/file/instance 名需检查源清单、实例连接、TB 层级探针、CModel trace、导出 manifest、DC 阶段识别、功耗注释等消费者。
- 重命名不顺便改变位宽、signed、运算顺序、流水/握手。不能用普通文本替换把指数域与指数宽度混为一个名称。
- RTL 源内容变化需要新快照和相应验证；不能因“仅改名”跳过既有门禁，不能直接修改历史导出或旧结果。冻结 SV 不同步。
- 纯文档规则更新检查 skill、链接及冲突；实际 RTL/接口改名再按影响范围回归，EDA 仍使用新快照及真实证据。
