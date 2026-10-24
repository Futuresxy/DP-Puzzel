---
name: chisel-design
description: 在 DP-Puzzel 中迁移、审查五族六种基础PE及K/MN编排，维护逐文件 spec，检查数值位宽、资源共享、接口与流水契约。
---

# Chisel 设计与规格协同

先读取根目录 [AGENTS.md](../../AGENTS.md)、[源码导航](../../hw/chisel_src/README.md) 和目标文件对应的 spec；当前可执行范围以用户本轮授权为准。

- `hw/chisel_src/<relative>.scala` 必须一一对应 `hw/spec/<relative>.md`，辅助 object、Bundle、参数和生成/展开入口也不例外。新增、重命名、删除、修改必须同步维护两者及导航。
- 五族目录为pe/PE_H、PE_Q、PE_E、PE_HQE、PE_QE，每族独立SubPE/PEGroup/DataUnpack/PE；公共接口/算术/C-D放Utils，Scala package小写。用户指定的下划线族名优先于原通用UpperCamelCase习惯。
- 仅六个合法profile：H/Q/HQE/QE的g4，E的g4/g2。原MidGroup叫PE，g表示PG数量；保留实际实例边界。
- HQE/QE/E保留源分级组织；H/Q使用16/32路产品统一对齐、流水自然位宽加法树，PG不做局部和。H/Q最终规范化后明确RTZ到公共F，不能宣称与分级路径bit-exact。
- 统一PE结果为sign/magnitude/top_anchor/zero/special，F=pe_align_width，11级；g2规范化magnitude末尾补一个低0保持anchor，精确对齐g4。K/MN公共C-D总18级；不写阵列。
- AlignmentConfig默认28/2/40/40，公开Q字内窗口26..30、PG guard2..4、PE窗口38..48、top窗口38..48且≥PE。默认<JSON<CLI，静态非法值require拒绝；运行硬件约束assert。乘法/加法按自然增长，无任意乘/加输出位宽旋钮。
- spec必须记录S/I/F、anchor含义、scale、资源、各级周期、valid/复位、截断位置与状态。H/Q删掉的字内/PG参数不应重新生成电路；输出layout和保留位数相同只是公平比较条件之一。
- 可调参数集中在 `hw/chisel_src/config/Parameters.scala`，从 `hw/configs/*.json` 传入。生成命令选择配置即可改变 RTL，不要求手改 PE 电路；固定数值/流水合同与可调参数分开。配置严格校验并随导出 manifest 保存完整有序布局、源码和工具指纹。
- 拷贝前先读懂原始解码、固定点、scale 范围、共享乘法器和控制。保留来源 commit/文件 hash；去掉隐式环境参数，接口适配逐项记录，不把迁移/风格统一称为完成微架构优化。
- 参数和 Scala 方法用 lowerCamelCase；硬件信号 lower_snake_case，寄存器 `_q`，端口 `in`/`out`。一个 Module 一个同名 Scala 文件；注释优先说明位宽依据和取舍。
- 所有移位、舍入、扩展和裁剪给出依据。结构性零位裁剪与有损 RTZ 对齐分开描述。特殊值和零不能污染 MAX anchor；不同 scale block 不能错误合并。
- 说明 ready/valid 的真实语义。没有反压的流水使用 Valid，不能把忽略 ready 的路径伪装为 Decoupled；运行格式若按事务采样，则控制必须和数据同步流水。
- Scala 编译/CHIRRTL 展开只确认结构可生成。没有 SV testbench 对对应导出 RTL 的精度/周期验证，不标记 passed、不进入 DC/power、不继承参考项目的通过状态。源码审查阶段不擅自扩展到实验或性能结论。

当前基线与待验收边界见 [六种PE设计](../../hw/spec/six-pe-design.md)；[旧迁移说明](../../hw/spec/pe-migration.md) 仅用于历史对照。未来流水或位宽发生变化时，先同步规格和验收计划，再决定需要的验证。
