# 硬件规格

当前实现为五族六种基础 PE：PE_HQE_g4、PE_QE_g4、PE_H_g4、PE_Q_g4、PE_E_g4、PE_E_g2。HQE/QE/E 保留分级复用，H/Q 采用全局对齐；阵列仍处于调研讨论阶段。

| 入口 | 内容 |
| --- | --- |
| [六种 PE 设计](six-pe-design.md) | 当前层级、数值坐标、周期、参数与 K/MN 编排合同 |
| [本轮检查记录](six-pe-checks.md) | 编译、展开与有限 RTL 定向检查的证据和限制 |
| [当前迁移来源](six-pe-source.json) | 原工程固定 commit、文件指纹与迁移调整 |
| [集中参数](config/Parameters.md) | 四个对齐参数、合法范围及 JSON/CLI 优先级 |
| [目标格式与待核验项](precision-formats.md) | 外部格式来源、数值语义与尚未确定的规范 |
| [逐文件索引](../chisel_src/README.md) | 52 组 Scala/spec 对应关系 |
| [模块规格模板](module_template.md) | 新增模块时填写的规格字段 |

逐文件 spec 与源码保持同路径：`pe/PE_H`、`pe/PE_Q`、`pe/PE_E`、`pe/PE_HQE`、`pe/PE_QE` 为专用通路；`Utils` 为公共接口、算术与 C/D；`core` 为 K_PE/MN_PE；`config` 和 `elaborate` 为参数与生成工具。

阵列参考保存在用户整理的 `array_ref/`，这些文档不构成阵列实现授权：

- [阵列方案讨论](array_ref/array-design-discussion.md)
- [OS 与跨指令调度调研](array_ref/os-array-scheduling-research.md)
- [Ascend Cube 调度对照](array_ref/ascend-cube-scheduling-research.md)
- [官方 Ascend MMAD ISA 编译核验](array_ref/ascend-official-mmad-isa-analysis.md)

旧扁平 PE 与旧 Full 四层方案的迁移说明、检查记录已移出当前工作树，可从 Git 历史查阅。[旧扁平来源指纹](migration-source.json)和[旧 Full 来源指纹](full-reuse-source.json)保留用于追溯，其目标路径属于历史版本，不能作为当前源码映射或验证证据。

完整 SV 数值/周期回归、EDA 与 characterization 尚未完成，有限定向检查不等于完整精度验收。
