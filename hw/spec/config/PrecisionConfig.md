# PrecisionConfig.scala：Full 能力集合

对应源码：[PrecisionConfig.scala](../../chisel_src/config/PrecisionConfig.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

不可变 `PEPrecisionConfig` 保留源解包所需的 FP16/BF16/FP8/FP6/E2M1/NVFP4/HiF4 capability 字段和 supportsDataType 查询。Full-only 迁移只导出 `PEPrecisionConfigs.fullSupport`，各项均为 true；没有带入专用 BF16、Q-only、E-only 或 Low 模块。

Scala 构造要求至少一项能力；supportsDataTypeCode 为 host 查询，supportsDataType 在硬件中组合比较 W4 格式码，两者语义应一致。位宽与编码由 Parameters 固定，没有流协议、时钟、复位或寄存器。能力集合不是运行时模式寄存器；full 硬件各模式复用同一资源且互斥使用。

后续若重新开放裁剪 variant，须另定结构、完整 spec、独立 config 和 RTL 回归，不能仅设置一个布尔值便宣称专用实现已迁移。当前仅检查 Full 实例能构造，数值模式仍待 SV 验收。
