# 命名规范来源与现有代码审查

参考：superscalarNPU 的 `.claude/skills/sn-naming-convention/SKILL.md`，按用户要求于 2026-11-06 阅读。参考仓库 HEAD 为 `995090913411aa354bd3785316abe848c329009d`，读取文件 SHA-256 为 `3b262212a9fc8dbafae82e56b249aaae9c56691dfae6c23f69c4e07aea447546`；hash 标识实际文本，不假定参考工作区干净。

## 保留与适配

| 原规范内容 | DP 对应 |
| --- | --- |
| sn_ 前缀及命名维度表 | dp_ 模块/RTL 文件/共享宏；保留现有功能目录和稳定入口 |
| box 对照表及新增清单 | 替换为 top/group/lane/unpack/arithmetic 和共享后端 |
| moduleA_moduleB 接口前缀 | 保留在父层互联线上；模块自身端口继续 in_/out_，内部变量按功能命名 |
| 单 bit、多 bit、槽位命名 | 保留，并加入阶段和 operand/group/lane 轴 |
| valid/ready 与 stall 反向命名 | 保留方向原则；只在接口实际定义时使用，不给 DP 内部新增反压 |
| 写回/唤醒 | 对应 DP 结果返回，保留方向/功能含义；不引入 OOO 系统 |
| CRF 多端口 | 对应操作数 A/B/C、scale、多 lane/group 区分；不新增 CRF |
| 接口组 driver2receiver | 保留作为文档分组，RTL 互联名仍以下划线连接 |
| CSV 表头、注释、文件名 | 保留详细格式；按 DP 版本/文件规则适配，现有 Markdown 可表达相同信息 |
| 两类审查清单 | 保留并扩展内部变量语义、SIF、d/q 和重命名依赖 |

本项目不存在原规范的 SN box、build.py target、OOO/CRF 接口；不能照搬为已实现内容。完整主体规则在同目录上级 SKILL.md，code-style 只链接它并保持工程规则一致。

## 当前代码的语义核对（未执行改名）

定位基于当前工作区，后续行号可能移动；以文件、作用域和表达式共同定位。

| 文件/作用域 | 旧名 | 实际含义 | 建议 |
| --- | --- | --- | --- |
| `src/verilog/unpack/dp_operand_unpack.v`，编码分解 | e | `(raw >> fb) & ((1 << eb) - 1)`，原始指数域 | exponent_field |
| 同上 | f | `raw & ((1 << fb) - 1)`，不含隐含位的 fraction | fraction_field |
| 同上 | eb / fb | 由 datatype 决定的指数域/fraction 域宽度 | exponent_field_width / fraction_field_width |
| 同上 | raw / n | 输入编码片段 / 已解码 DP 数值 token | operand_bits / decoded_number |
| `src/verilog/arithmetic/dp_max_tree.v`，g_branch | a / b | left_tree / right_tree 的 out_max | left_max / right_max |
| 同上 | va / vb | 两个子树 out_active | left_active / right_active |
| `src/verilog/arithmetic/dp_sum_tree.v`，g_pair | a / b | 2*i、2*i+1 对应输入叶值 | pair_left_value / pair_right_value |
| `src/verilog/lane/dp_lane_e.v`，g_pair | a / b | 成对的有符号 product | product_even / product_odd |
| `src/verilog/parameter/dp_functions.vh`，格式相关函数 | t | 传入的 datatype | datatype |

这些例子说明不能全局替换 `a` 或 `f`：它们在不同作用域表示不同内容。源代码里 `in_a` 表示数学操作数 A、模块 `_e` 表示 E 专用族，均属于有定义的名字，不能一并误改。

`group_fraction` 中局部 f 是定点小数位数而非编码 fraction 域，进一步迁移需单独核对函数公式；不可用上表的 fraction_field 无差别替换。

## 本次验证范围

本次只建立命名 skill 并更新 AGENTS、code-style 和 README 的引用。检查主体格式、文件链接、术语/后缀冲突及上述源码语义。没有重命名 RTL/CModel，没有运行生产功能回归或 EDA，也没有宣称全仓库命名已经符合规范。后续源码迁移须按 skill 的依赖核对与验证规则执行。
