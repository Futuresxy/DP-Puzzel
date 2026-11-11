---
name: chisel-design
description: 按 DP-Puzzel 的共同规格开发和审查 Chisel，校验数值位宽、共享资源、接口、流水及验证证据。
---

# Chisel 设计与规格协同

先读取 [AGENTS.md](../../AGENTS.md)、[Chisel 入口](../../src/chisel/README.md) 与目标模块的 [共用规格](../../src/spec/README.md)。在 `src/chisel/` 维护源码与参数，在 `src/spec/` 建立模块与实现的映射。变更数值、资源、接口或周期时同步规格及验证计划。

- 拷贝前先读懂原始解码、固定点、scale 范围、共享乘法器和控制。保留来源 commit/文件 hash；去掉隐式环境参数，接口适配逐项记录，不把迁移/风格统一称为完成微架构优化。
- 参数和 Scala 方法用 lowerCamelCase；硬件信号 lower_snake_case，寄存器 `_q`，端口 `in`/`out`。一个 Module 一个同名 Scala 文件；注释优先说明位宽依据和取舍。
- 所有移位、舍入、扩展和裁剪给出依据。结构性零位裁剪与有损 RTZ 对齐分开描述。特殊值和零不能污染 MAX anchor；不同 scale block 不能错误合并。
- 说明 ready/valid 的真实语义。没有反压的流水使用 Valid，不能把忽略 ready 的路径伪装为 Decoupled；运行格式若按事务采样，则控制必须和数据同步流水。
- Scala 编译/CHIRRTL 展开只确认结构可生成。没有 SV testbench 对对应导出 RTL 的精度/周期验证，不标记 passed、不进入 DC/power、不继承参考项目的通过状态。源码审查阶段不擅自扩展到实验或性能结论。

RTL 导出至 `hw/rtl/<export-id>/`，由根 `test/` 验证。旧 PE 实现及其合同从 Git 历史查阅。
