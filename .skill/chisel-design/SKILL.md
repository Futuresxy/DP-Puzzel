---
name: chisel-design
description: 在 DP-Puzzel 中设计、迁移或审查 PE、MN-PE、K-PE 的 Chisel 硬件，维护同路径逐文件 spec，检查数值位宽、资源共享、接口与流水契约。
---

# Chisel 设计与规格协同

先读取根目录 [AGENTS.md](../../AGENTS.md)、[源码导航](../../hw/chisel_src/README.md) 和目标文件对应的 spec；当前可执行范围以用户本轮授权为准。

- `hw/chisel_src/<relative>.scala` 必须一一对应 `hw/spec/<relative>.md`，辅助 object、Bundle、参数和生成/展开入口也不例外。新增、重命名、删除、修改必须同步维护两者及导航。
- 目录按职责分为 config（参数/格式）、common（接口/可复用算术）、pe（PE）、core（MN/K-PE 和 C/D）、elaborate（检查/生成）。package 与目录一致；不要把所有文件集中进 pe，也不要把源码分目录误解为恢复旧硬件层级。
- spec 写明：为何采用该架构、物理资源与复用、端口和合法参数、数值编码/scale、每段 W/S/I/F 或等价数值公式、精度损失位置、逐级流水与 valid/复位、边界行为、验证状态。解释设计理由，避免逐行翻译代码。
- 保持 PE 和 MN-PE/K-PE 两层计算架构。PE 内展开旧 SubPE/PEGroup 的计算，基本算术可复用 object 函数或有独立职责的基础模块；不能换个名称恢复旧层级。MN-PE 是一个 PE+C/D，K-PE 为 1–4 个 PE 共享 C/D。
- 参数直接用实际容量 `h/q/e`，如 `PEConfig(16,32,64)`。H/Q/E 是运行模式容量，不能相加成为同时可用吞吐。K 顶层以合计 K 命名，内部有序布局另记录；MN 不增加 PE 数量后缀。
- 可调参数集中在 `hw/chisel_src/config/Parameters.scala`，从 `hw/configs/*.json` 传入。生成命令选择配置即可改变 RTL，不要求手改 PE 电路；固定数值/流水合同与可调参数分开。配置严格校验并随导出 manifest 保存完整有序布局、源码和工具指纹。
- 拷贝前先读懂原始解码、固定点、scale 范围、共享乘法器和控制。保留来源 commit/文件 hash；删除过时兼容接口和隐式环境参数，不能只批量改名后宣称完成重构。
- 参数和 Scala 方法用 lowerCamelCase；硬件信号 lower_snake_case，寄存器 `_q`，端口 `in`/`out`。一个 Module 一个同名 Scala 文件；注释优先说明位宽依据和取舍。
- 所有移位、舍入、扩展和裁剪给出依据。结构性零位裁剪与有损 RTZ 对齐分开描述。特殊值和零不能污染 MAX anchor；不同 scale block 不能错误合并。
- 说明 ready/valid 的真实语义。没有反压的流水使用 Valid，不能把忽略 ready 的路径伪装为 Decoupled；运行格式若按事务采样，则控制必须和数据同步流水。
- Scala 编译/CHIRRTL 展开只确认结构可生成。没有 SV testbench 对对应导出 RTL 的精度/周期验证，不标记 passed、不进入 DC/power、不继承参考项目的通过状态。源码审查阶段不擅自扩展到实验或性能结论。

当前迁移架构及尚待验证的数值边界见 [迁移说明](../../hw/spec/pe-migration.md)。未来流水或位宽发生变化时，先同步规格和验收计划，再决定需要的验证。
