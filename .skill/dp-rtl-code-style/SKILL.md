---
name: dp-rtl-code-style
description: Design, refactor, or review maintained DP-Puzzel Verilog RTL using project declaration, synchronous active-low reset, parameterized pipeline DFF, numeric-format, and verification conventions.
---

# DP RTL Code Style

适用于维护中的手写 Verilog：多精度 DP、E 前端和共享模块。先读根目录 `AGENTS.md`、`src/verilog/README.md` 和目标模块 spec。不修改冻结的 `src/verilog/systemverilog/`，不将此规则直接套用到 Chisel 默认端口或第三方源码。

参考用户指定的 `sn-rtl-code-style`，按 DP 的语言、接口和验证合同重新编写；采纳范围及差异见 [参考适配说明](references/sn-adaptation.md)。后续实现寄存器时使用 [DFF 合同与模板](references/registers.md)，不要直接导入 SN 的异步复位或私有路径。

## 编写与审查

1. 使用 Verilog-2005：`wire/reg`、`always @*`、`always @(posedge clock)`，不引入 SV 专用语法。每个 module 独立同名文件，加入相关显式 `files.f` / `files_e.f`；实例使用具名参数和端口连接。
2. **每条声明只定义一个变量，每个端口占一行且重复完整方向、类型和位宽。** `wire/reg/integer/genvar/parameter/localparam` 同样适用。长表达式可以换行，禁止用逗号合并多个声明对象；端口列表、连接、拼接和实参中的语法逗号不受此限制。每行一个赋值语句，实例的每个参数/端口连接也独占一行，包括 DFF；例子见 [编码细则](references/coding-style.md)。
3. 使用两空格、UTF-8、LF、100 列目标行宽。模块使用 `dp_` 前缀，宏使用 `DP_` 前缀；模块和信号用 `lower_snake_case`，参数用 `UPPER_SNAKE_CASE`；端口 `in_` / `out_`，下一状态 `_d`、寄存输出 `_q`、使能 `_en`、低有效 `_n`。时钟为 `clock`，复位为 `rst_n`；流水信号保留阶段，如 `sum_s7_d` / `sum_s7_q`；DFF 实例使用 `ff_` 前缀并标出边界，如 `ff_s6_s7_sum`。名字表达数值/控制功能，不只描述来源。
4. **复位统一同步低有效 `rst_n`。** 只在时钟上升沿采样，不加 `negedge rst_n`。复位优先于使能，清空有效控制并取消在途；无需初始化的数据寄存器不复位。详见 [复位与流水寄存器](references/registers.md)。
5. **每层流水寄存器统一实例化参数化 DFF 模块**，分别提供控制复位和数据使能版本。时序赋值集中在 DFF 原语内，功能层保留组合计算与具名 DFF 实例；不使用宏替代 module 边界。每个实例承载同 clock/reset/enable 语义的一组位，不按每 bit 实例化。不增加流水拍数或改变 II。
6. 简单组合表达式优先 `assign`，译码/多分支/循环计算允许 `always @*`，使用阻塞赋值和完整默认赋值，条件和循环写 `begin/end`，`case` 明确默认行为。DFF 内用非阻塞赋值；信号单一驱动。禁止锁存器、组合环、隐式网络、`casex`、综合路径中的延迟或运行时软件模型；不用 X 或综合指示掩盖未实现分支。
7. 明确操作数和结果的宽度、signed/unsigned、扩展、截断、移位及舍入。先扩展再运算，不能指望 `$signed` 自动加宽；拼接后的算术类型显式处理。数据路径常量写明宽度，尺寸推导可用 integer。参数检查避免零宽、负复制数和越界，非法配置明确拒绝；支持范围以 spec 和验证为准。
8. 模块注释说明功能、接口、流水归属、延迟/II、复位和数值语义。乘法器、树、移位器及级间接口使用逐精度 S/I/F 表，注明 TC/SM、总宽、二进制点、补零/截位和指数坐标。每行一种或一类精度，位宽随 `K_FP16/LOCAL_W/GLOBAL_W` 推导，不复制硬编码默认值。
9. 保持数据与 valid/type/last/sign/anchor/special 对齐。无背压流水每拍推进 valid，气泡清零 valid，payload 仅有效时更新；数据保持不等于全流水停顿。规约使用平衡树；时序优化依据实测关键路径，DFF 封装不自动改善 PPA。
10. 固定格式/编码/跨模块布局集中在 `parameter/*.vh`，宏只在头文件定义；局部计算用具名派生 `localparam`，不建立无意义宏别名。独立接口字段分别命名；内部 DFF 打包后紧邻解包，布局随参数推导，不散布裸数字切片。数组选择明确 MUX 规模/索引合法范围，不强制改成 one-hot 电路；详见编码细则。

## 验证与交付

- 检查分支、工作区与远程状态，保护用户变更；仅处理任务涉及文件，不顺带格式化冻结 SV 或快照。
- 先拆声明，再按 README 使用 Verible 排版。formatter 不替代声明/复位/DFF 结构审查。Verible lint 按 Verilog-2005 配置，不能为消除 lint 把代码改为 SV；数值/协议门禁继续使用 `test/run_verilog.py`。
- 纯规范修改检查文档、链接与 skill 格式即可。RTL 修改按影响范围执行严格语法/lint、数值、参数、断点和协议回归。共享流水/复位迁移覆盖多精度与 E 两个入口；新 DFF 验证复位优先、使能保持、气泡推进。
- 接口或层级变化同步 spec、TB、源清单、导出元数据及层级检查入口。新快照通过验证后才能进入 DC/功耗；不修改旧快照或继承旧 PPA。EDA 和记录保留遵从 AGENTS.md 及相应技能，不因风格修改自动运行 EDA。

审查输出聚焦违反规范的文件/行号、影响和建议，区分通过、失败、未检查。不机械声称全库符合新规则；修改涉及的声明、命名、布局、组合逻辑、DFF 边界、复位/使能、S/I/F 及验证证据均需检查，未改动的历史问题注明范围。

## 当前迁移状态（2026-11-06）

用户已确认单变量声明、同步低有效 `rst_n` 和 DFF 模块要求。当前已验证 RTL 仍使用同步高有效 `reset` 和功能模块内时序块；本次更新规范和可独立验证的 skill 模板，尚未迁移生产源码。模板不加入 DUT 清单，不构成 DP 功能/PPA 验收。后续按 [迁移验收](references/registers.md#迁移验收) 整批对齐依赖，不将旧接口误报为新规范已验收；完成后更新此状态和 README。
