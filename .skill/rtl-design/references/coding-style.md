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

查阅日期：2026-11-06。以下为风格/实现参考，未复制第三方源码或增加依赖。

- [lowRISC 风格指南](https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md)：参考具名连接、显式类型和组合/时序赋值分离。该指南主要面向 SV，采用异步低有效复位；本项目选择 Verilog-2005 和同步低有效复位，不照搬其语法和复位示例。
- [Verible lint](https://chipsalliance.github.io/verible/lint.html)：核对规则实际检查范围，命名检查不证明结构、数值或时序正确。
- [OpenTitan primitives](https://opentitan.org/book/hw/ip/prim/index.html)：参考参数化基础模块及通用/工艺实现分离；不构成本项目所有流水寄存器必须模块化的依据。

单变量声明、同步低有效 `rst_n`、流水寄存器统一 DFF 模块均为用户明确选择的项目规则。行为级时序块本身可推断 DFF，显式模块化是工程选择，不是 Verilog 语言强制要求。
