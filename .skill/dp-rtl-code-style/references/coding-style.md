# 声明、数值与工具细则

## 单变量声明

端口列表保留语法所需逗号，每行重复完整声明：

```verilog
input wire clock,
input wire rst_n,
input wire in_a_valid,
input wire in_b_valid,
input wire in_c_valid,
input wire [K_FP16*`DP_HALF_W-1:0] in_a,
input wire [K_FP16*`DP_HALF_W-1:0] in_b,
output wire out_valid
```

局部参数逐条以分号结束，不能写 `localparam integer A = ..., B = ...;`：

```verilog
localparam integer GROUP_W = LOCAL_W + 1 + $clog2(`DP_Q_LANES) + $clog2(`DP_LANES);
localparam integer GROUP_MAG_W = GROUP_W - 1;
localparam integer GLOBAL_MAG_W = GLOBAL_W - 1;
localparam integer N = GROUPS + 1;

wire [GROUP_W-1:0] group_sum_d;
wire [GROUP_W-1:0] group_sum_q;
```

模块参数列表每行写 `parameter integer NAME = ...`，项之间仍用逗号。内部变量、函数形参和数组同样不共享声明。初始化表达式/拼接中的逗号不属于多变量声明，不用简单“禁止逗号”的正则检查。

## 命名与文件组织

详细规则与允许的缩写/例外见 [dp-naming-convention](../../dp-naming-convention/SKILL.md)，此处只保留编码时的速查。

| 对象 | 规则 | 示例 |
| --- | --- | --- |
| 模块/文件 | `dp_` 前缀，同名；DFF 库类型后缀保留大写 | `dp_lib_DFFE.v` / `dp_lib_DFFE` |
| 普通实例 | `u_` 前缀加功能；已有实例无关改动不强制改名 | `u_lane_sum` |
| DFF 实例 | `ff_` 加源/目标阶段与内容 | `ff_s2_s3_payload`、`ff_s2_s3_valid` |
| generate | `g_` 加功能 | `g_group`、`g_lane` |
| 数据/控制信号 | 功能 + 阶段 + `_d/_q` | `group_magnitude_s5_q`、`valid_s3_d` |
| 父层互联线 | driver_receiver_function，必要时标实例索引和阶段 | `lane_group_sum_s4` |
| 使能/复位 | `_en` / `_n` | `payload_s3_en`、`rst_n` |
| 配置/派生参数 | 大写下划线 | `LOCAL_W`、`GROUP_MAG_W` |
| 头文件宏 | `DP_` 前缀 | `` `DP_HALF_W`` |

循环索引用 `lane_index/element_index/bit_index` 等，不用无含义 i/j 或 index1/index2；局部数值禁止 e/f/a 等，例外见命名 skill。

`_d/_q` 表示状态角色，不能替代功能名；避免 `tmp1`、只叫 `sram_d` 或无含义的 `bus0`。`in_a/in_b/in_c` 是已定义的操作数角色，可以保留。`*_s3_d` 是即将存入 S3 的组合结果，`*_s3_q` 是 S3 寄存输出；实例 `ff_s2_s3_*` 明确其 S2→S3 边界。

保持 `src/verilog/{top,group,lane,unpack,arithmetic,parameter}`；共享 DFF 后续落实到 `src/verilog/common/`，不复制 SN 的 box 目录。每个模块依次组织：功能/协议和 SIF 注释、参数/端口、局部参数、信号、组合计算、按 S1…S8 顺序的级间 DFF、输出连接。大型流水模块可按阶段重复“组合计算→DFF”，不要拆散相关逻辑。

## 常量、接口打包与选择逻辑

- 有架构意义的数值必须命名：编码、精度宽度、容量、字段边界等。跨模块固定常量放 `.vh`，局部推导用 `localparam`。0/1、显式位宽的复位值和有解释的算法常数无需为命名而增加间接层；不将所有 localparam 改成全局宏。
- `.v` 不定义新宏；`.vh` 使用 include guard 和 `DP_` 前缀。已有宏不建立同义别名，类型/宽度转换需明确转换目的，不算纯同义别名。
- 独立字段优先独立端口。既有参数化扁平向量接口可保留，使用具名宽度、偏移或 `base +: FIELD_W`；固定共享布局定义在 `.vh`，参数化布局用公式，禁止用全局宏冻结可变位宽。
- DFF 内部可临时打包同使能/复位语义的字段；紧邻实例用命名 wire 解包，保持拼接顺序一致。不同使能不能合并，valid 与 payload 默认分开；见级间模板。
- 按主体规范，新功能组合逻辑用 `assign` 与显式模块/generate，功能层仅 FSM 次态允许 `always @*`。已有复杂组合块后续逐模块等价迁移；不为凑形式制造串行三目链。
- 按主体规范，功能条件显式归约/比较为单 bit 后使用 `&/|/~`。这是项目风格选择，不表示逻辑运算语言无效；迁移不得机械替换多位表达式，需保留四态语义。
- 常量索引/generate 切片允许。动态选择按主体规范显式组织 MUX/选择树，写明路数、宽度、越界行为；one-hot 保证或检查互斥，不能用 OR 合并掩盖多选错误。

## 数值和边界

- 总线通常用 `[W-1:0]`，端序和打包布局写在合同中。运算前显式零扩展/符号扩展，运算后明确保留位。
- 区分 TC 二补码与 SM 符号/幅值；取绝对值考虑最小负值及容器宽度。区分逻辑右移与算术右移，验证移位超过宽度的情况。
- S/I/F 中 S 不计入 I；无符号幅值 S=0，sign 单独传递。高位扩展不增加 F，低位补零增加 F；不能仅靠总线宽度推断最终精度。各节点格式表必须来自该节点实际数值合同。
- elaboration 参数选择与运行时 datatype 选择分开；不固定 valid/datatype 等功能输入简化电路。
- 全部网络显式声明。若采用 `` `default_nettype none``，文件末恢复默认，验证全清单，不无验证地改变全库编译语义。

## 工具边界

Verible 用于排版及部分风格检查，Verilator/严格 Verilog-2005 编译用于硬件诊断，testbench 用于数值和周期验收。

已检查本地 Verible `v0.0-4298-g085eef05` 的 `--help_rules=all`：没有可直接替代本项目“单声明单对象”审查的专用规则；`dff-name-style` 只检查命名，不验证 DFF module 使用。不要宣称 formatter 已完成这两项门禁。

接入 Verible lint 时，关闭要求 `always_comb` 的 `always-comb`，参数命名接受 `UPPER_SNAKE_CASE`，不启用与 `in_` / `out_` 冲突的 `_i` / `_o` 强制后缀。其他规则先核对工具版本与 Verilog-2005 兼容性，再决定是否作为门禁。

## 来源与项目选择

查阅日期：2026-11-06。以下为之前查阅的补充资料；当前规则主体以移植后的 SN 规范为准，差异见 [移植记录](sn-adaptation.md)。

- [lowRISC 风格指南](https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md)：参考具名连接、显式类型和组合/时序赋值分离。该指南主要面向 SV，采用异步低有效复位；本项目选择 Verilog-2005 和同步低有效复位，不照搬其语法和复位示例。
- [Verible lint](https://chipsalliance.github.io/verible/lint.html)：核对规则实际检查范围，命名检查不证明结构、数值或时序正确。
- [OpenTitan primitives](https://opentitan.org/book/hw/ip/prim/index.html)：参考参数化基础模块及通用/工艺实现分离；不构成本项目所有流水寄存器必须模块化的依据。

单变量声明、同步低有效 `rst_n`、流水寄存器统一 DFF 模块均为用户明确选择的项目规则。行为级时序块本身可推断 DFF，显式模块化是工程选择，不是 Verilog 语言强制要求。
