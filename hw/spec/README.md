# 硬件规格职责

先确定数值语义和接口，再设计结构。每个 `hw/chisel_src/<relative>.scala` 对应本目录下 `<relative>.md`，包括参数、Bundle、辅助函数和展开/生成入口。新文件可从 [module_template.md](module_template.md) 开始。

| 文件 | 职责 |
| --- | --- |
| precision-formats.md | 目标格式清单、来源与需要明确的精度语义 |
| module_template.md | 单模块接口、数值、时序和验证规格模板 |
| [pe-migration.md](pe-migration.md) | 本轮两层 PE 架构迁移、来源与待验收边界 |
| [config/Parameters.md](config/Parameters.md) | 集中式生成参数与合法范围 |
| [array-design-discussion.md](array-design-discussion.md) | 待审查的 2×2 分组阵列、M8N32 指令切分、L0 layout 和 GEMM 调度；尚无阵列代码 |
| [os-array-scheduling-research.md](os-array-scheduling-research.md) | 指令内部 OS 调度：论文/逆向/公开 RTL 证据，本地累加、context 交错、preload/compute/drain 和反馈结构候选 |
| config/、common/、pe/、core/、elaborate/ | 与 Chisel 源码目录镜像的逐文件架构说明；完整索引见 [源码导航](../chisel_src/README.md) |

规格必须区分物理实现、支持的数值模式与运行模式；BF16/FP16、MXFP8/6、MXFP4/NVFP4/HiF4 不能仅以输入位宽代替完整定义。当前 PE 的参数、流水和数值合同已写入对应 spec，但不表示 RTL 验证/PPA 已通过。
